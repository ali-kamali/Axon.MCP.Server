"""Build call graph relationships in database."""

import asyncio
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Symbol, File, Relation, Repository
from src.database.session import AsyncSessionLocal
from src.config.enums import SymbolKindEnum, RelationTypeEnum, LanguageEnum, SourceControlProviderEnum
from src.extractors.call_analyzer import CSharpCallAnalyzer, JavaScriptCallAnalyzer, Call
from src.extractors.call_resolver import CallResolver
from src.parsers.roslyn_integration import RoslynAnalyzer
from src.gitlab.repository_manager import RepositoryManager
from src.azuredevops.repository_manager import AzureDevOpsRepositoryManager
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class CallGraphBuilder:
    """Builds call graph relationships for repository."""
    
    def __init__(self, session: AsyncSession):
        """
        Initialize call graph builder.
        
        Args:
            session: Database session
        """
        self.session = session
        self.csharp_analyzer = CSharpCallAnalyzer()
        self.js_analyzer = JavaScriptCallAnalyzer()
        self.resolver = CallResolver(session)
        # Don't create RoslynAnalyzer here - it must be created in the async context
        # to avoid "Task attached to a different loop" errors
    
    async def build_call_relationships(
        self,
        repository_id: int
    ):
        """
        Build call relationships for entire repository.
        
        Args:
            repository_id: Repository ID
        """
        logger.info("building_call_relationships", repository_id=repository_id)
        
        # Create RoslynAnalyzer in the current async context to avoid loop errors
        roslyn_analyzer = RoslynAnalyzer()
        
        # Warmup: Send a ping to ensure Roslyn process is fully initialized
        # This eliminates the 7 startup transient errors that occur in files 2-8
        if roslyn_analyzer.is_available():
            try:
                await roslyn_analyzer._send_request({"operation": "ping"}, timeout=5)
                logger.debug("roslyn_warmup_successful")
            except Exception as e:
                logger.debug("roslyn_warmup_failed", error=str(e))
                # Continue anyway - warmup failure is not critical
        
        # Get repository
        result = await self.session.execute(
            select(Repository).where(Repository.id == repository_id)
        )
        repo = result.scalar_one_or_none()
        
        if not repo:
            logger.error("repository_not_found", repository_id=repository_id)
            return 0
        
        # Get repository path on disk based on provider
        if repo.provider == SourceControlProviderEnum.AZUREDEVOPS:
            # Azure DevOps uses a different cache structure
            if not repo.azuredevops_project_name:
                logger.error(
                    "azuredevops_project_name_missing",
                    repository_id=repository_id,
                    repo_name=repo.name
                )
                return 0
            repo_manager = AzureDevOpsRepositoryManager()
            repo_path = repo_manager.get_repository_path(repo.azuredevops_project_name, repo.name)
        else:
            # GitLab uses path_with_namespace
            repo_manager = RepositoryManager()
            repo_path = repo_manager.cache_dir / repo.path_with_namespace.replace("/", "_")
        
        # Initialize Roslyn if possible
        try:
            # Find solution file
            sln_files = list(repo_path.glob("*.sln"))
            if sln_files:
                logger.info("loading_roslyn_solution", solution=str(sln_files[0]))
                await roslyn_analyzer.open_solution(str(sln_files[0]))
            else:
                # Find project files - simplified strategy: pick first or don't load
                csproj_files = list(repo_path.glob("**/*.csproj"))
                if csproj_files:
                    # Loading random project might be weird. 
                    # Ideally we load the one relevant for the file, but we have one global context.
                    # Let's load the first one found in root or just log warning.
                    logger.info("loading_roslyn_project", project=str(csproj_files[0]))
                    await roslyn_analyzer.open_project(str(csproj_files[0]))
        except Exception as e:
            logger.warning("roslyn_initialization_failed", error=str(e))
        
        # Get all methods/functions in repository
        result = await self.session.execute(
            select(Symbol, File)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.kind.in_([
                    SymbolKindEnum.METHOD, 
                    SymbolKindEnum.FUNCTION,
                    SymbolKindEnum.PROPERTY,
                    SymbolKindEnum.VARIABLE
                ])
            )
        )
        
        rows = result.all()
        
        # Group symbols by file
        files_map: Dict[int, File] = {}
        file_symbols: Dict[int, List[Symbol]] = defaultdict(list)
        
        for symbol, file in rows:
            files_map[file.id] = file
            file_symbols[file.id].append(symbol)
            
        total_files = len(files_map)
        total_methods = len(rows)
        
        logger.info(
            "call_graph_analysis_started",
            repository_id=repository_id,
            total_files=total_files,
            total_symbols=total_methods
        )
        
        # Process files in parallel with semaphore
        semaphore = asyncio.Semaphore(10)  # Limit concurrency to 10 files
        processed_files = 0
        relationships_created = 0
        
        # Create tasks for all files
        tasks = []
        for file_id, symbols in file_symbols.items():
            file = files_map[file_id]
            task = self._process_file_safe(
                semaphore,
                file,
                symbols,
                repo_path,
                roslyn_analyzer
            )
            tasks.append(task)
        
        # Execute tasks in chunks to avoid creating too many tasks at once
        # and to allow periodic committing
        chunk_size = 50
        for i in range(0, len(tasks), chunk_size):
            chunk = tasks[i:i + chunk_size]
            results = await asyncio.gather(*chunk)
            
            # Aggregate results
            batch_relations = []
            for file_relations in results:
                if file_relations:
                    batch_relations.extend(file_relations)
            
            # Add to session and commit
            if batch_relations:
                self.session.add_all(batch_relations)
                relationships_created += len(batch_relations)
                await self.session.commit()
            
            processed_files += len(chunk)
            
            logger.info(
                "call_graph_progress",
                repository_id=repository_id,
                processed_files=processed_files,
                total_files=total_files,
                relationships_created=relationships_created
            )
        
        logger.info(
            "call_graph_completed",
            repository_id=repository_id,
            files_processed=processed_files,
            relationships_created=relationships_created
        )
        
        return relationships_created

    async def _process_file_safe(
        self,
        semaphore: asyncio.Semaphore,
        file: File,
        symbols: List[Symbol],
        repo_path: Path,
        roslyn_analyzer: RoslynAnalyzer
    ) -> List[Relation]:
        """Wrapper to process file with semaphore."""
        async with semaphore:
            return await self._process_file(file, symbols, repo_path, roslyn_analyzer)

    async def _process_file(
        self,
        file: File,
        symbols: List[Symbol],
        repo_path: Path,
        roslyn_analyzer: RoslynAnalyzer
    ) -> List[Relation]:
        """
        Process a single file: parse once and analyze all symbols.
        
        Args:
            file: File record
            symbols: List of symbols in this file
            repo_path: Repository root path
            roslyn_analyzer: RoslynAnalyzer instance
            
        Returns:
            List of Relation objects to create
        """
        relations = []
        
        # Create a new session for this task to avoid concurrent usage of the shared session
        async with AsyncSessionLocal() as session:
            # Create a local resolver with the new session and roslyn analyzer
            local_resolver = CallResolver(session, roslyn_analyzer)
            
            try:
                file_path = repo_path / file.path
                
                if not file_path.exists():
                    logger.warning("file_not_found", file_path=str(file_path))
                    return []
                
                # Read file content
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        code = f.read()
                except Exception as e:
                    logger.warning("file_read_error", file_path=str(file_path), error=str(e))
                    return []
                
                # Parse the file to get AST
                from src.parsers import ParserFactory
                parser = ParserFactory.get_parser(file.language)
                
                # Use tree-sitter directly for AST
                # Handle different parser types:
                # - HybridCSharpParser: has tree_sitter attribute (which is a CSharpParser with parser attribute)
                # - CSharpParser/JavaScriptParser: has parser attribute directly
                tree = None
                if hasattr(parser, 'tree_sitter') and hasattr(parser.tree_sitter, 'parser'):
                    # HybridCSharpParser
                    tree = parser.tree_sitter.parser.parse(bytes(code, "utf8"))
                elif hasattr(parser, 'parser'):
                    # Regular parser (CSharpParser, JavaScriptParser, etc.)
                    tree = parser.parser.parse(bytes(code, "utf8"))
                else:
                    logger.warning(
                        "parser_no_tree_sitter",
                        file_path=file.path,
                        parser_type=type(parser).__name__,
                        parser_attrs=dir(parser)[:10]  # Show first 10 attributes for debugging
                    )
                    return []
                
                if tree:
                    # Extract imports if parser supports it
                    imports = []
                    if hasattr(parser, 'extract_imports'):
                        imports = parser.extract_imports(tree.root_node, code)
                    
                    # Fetch field/property symbols for this file to build field_types map
                    field_types = {}
                    result = await session.execute(
                        select(Symbol)
                        .where(
                            Symbol.file_id == file.id,
                            Symbol.kind.in_([SymbolKindEnum.VARIABLE, SymbolKindEnum.PROPERTY])
                        )
                    )
                    field_symbols = result.scalars().all()
                    
                    # Build map of field name -> type
                    for field_symbol in field_symbols:
                        if field_symbol.return_type:
                            # Use simple name (e.g., _service -> IUserService)
                            field_types[field_symbol.name] = field_symbol.return_type
                    
                    # Process each symbol in the file
                    symbols_processed = 0
                    symbols_with_nodes = 0
                    total_calls_detected = 0
                    total_calls_resolved = 0
                    
                    for symbol in symbols:
                        symbols_processed += 1
                        
                        # Find the symbol's node in the tree
                        symbol_node = self._find_symbol_node(tree.root_node, symbol, code)
                        
                        if symbol_node:
                            symbols_with_nodes += 1
                            
                            # Extract calls based on language
                            calls = await self._extract_calls_for_symbol(
                                symbol_node,
                                code,
                                file.language
                            )
                            
                            total_calls_detected += len(calls)
                            
                            # Resolve and create relationships
                            for call in calls:
                                target_id = await local_resolver.resolve_call_target(
                                    call,
                                    symbol,
                                    file,
                                    imports,
                                    field_types,
                                    code
                                )
                                
                                if target_id:
                                    # Target is guaranteed to exist as it was resolved from DB
                                    total_calls_resolved += 1
                                    
                                    # Create CALLS relationship
                                    relation = Relation(
                                        from_symbol_id=symbol.id,
                                        to_symbol_id=target_id,
                                        relation_type=RelationTypeEnum.CALLS,
                                        relation_metadata={
                                            'is_async': call.is_async
                                        },
                                        start_line=call.line_number,
                                        end_line=call.end_line,
                                        start_column=call.start_column,
                                        end_column=call.end_column
                                    )
                                    relations.append(relation)
                                    
                            # Extract usages based on language
                            usages = await self._extract_usages_for_symbol(
                                symbol_node,
                                code,
                                file.language
                            )
                            
                            for usage in usages:
                                target_id = await local_resolver.resolve_usage_target(
                                    usage.method_name, # method_name holds the variable name
                                    symbol,
                                    file,
                                    imports,
                                    receiver=usage.receiver,
                                    field_types=field_types
                                )
                                
                                if target_id:
                                    # Target is guaranteed to exist
                                    # Create USES relationship
                                    relation = Relation(
                                        from_symbol_id=symbol.id,
                                        to_symbol_id=target_id,
                                        relation_type=RelationTypeEnum.USES,
                                        start_line=usage.line_number,
                                        end_line=usage.end_line,
                                        start_column=usage.start_column,
                                        end_column=usage.end_column
                                    )
                                    relations.append(relation)
                        else:
                            # Log when we can't find the node
                            logger.debug(
                                "symbol_node_not_found",
                                symbol_name=symbol.name,
                                start_line=symbol.start_line,
                                file_path=file.path
                            )
                    
                    # Log summary for this file (INFO level so it shows in logs)
                    if symbols_processed > 0:
                        logger.info(
                            "file_call_analysis_summary",
                            file_path=file.path,
                            symbols_processed=symbols_processed,
                            symbols_with_nodes=symbols_with_nodes,
                            calls_detected=total_calls_detected,
                            calls_resolved=total_calls_resolved,
                            relations_created=len([r for r in relations if r.from_symbol_id in [s.id for s in symbols]])
                        )
                                    
            except Exception as e:
                logger.error(
                    "file_processing_failed",
                    file_path=file.path,
                    error=str(e)
                )
            
        return relations
    
    def _find_symbol_node(
        self,
        root_node: "tree_sitter.Node",
        symbol: Symbol,
        code: str
    ) -> Optional["tree_sitter.Node"]:
        """
        Find the AST node for a symbol by line number.
        
        Args:
            root_node: Root of AST
            symbol: Symbol to find
            code: Source code
            
        Returns:
            Node for the symbol or None
        """
        # Simple heuristic: find node at symbol's start line
        # We use a non-recursive iterative approach or optimized traversal if possible
        # But for now, simple traversal is fine as we are already inside a per-file task
        
        target_line = symbol.start_line - 1 # 0-indexed
        
        # Optimization: Only search nodes that span the target line
        cursor = root_node.walk()
        
        visited_children = False
        while True:
            node = cursor.node
            
            # Check if this node contains the target line
            if node.start_point[0] <= target_line <= node.end_point[0]:
                # If it starts exactly on the line, check if it's a function
                if node.start_point[0] == target_line:
                    if node.type in [
                        'method_declaration', 'function_declaration',
                        'arrow_function', 'function', 'local_function_statement',
                        'lambda_expression', 'simple_lambda_expression', 'parenthesized_lambda_expression',
                        'constructor_declaration', 'field_declaration', 'property_declaration',
                        'variable_declarator'
                    ]:
                        return node
                
                # If we haven't visited children yet, go to first child
                if not visited_children and cursor.goto_first_child():
                    continue
            
            # Try next sibling
            if cursor.goto_next_sibling():
                visited_children = False
            elif cursor.goto_parent():
                visited_children = True
            else:
                break
                
        return None
    
    async def _extract_calls_for_symbol(
        self,
        symbol_node: "tree_sitter.Node",
        code: str,
        language: LanguageEnum
    ) -> List[Call]:
        """Extract calls from symbol based on language."""
        if language == LanguageEnum.CSHARP:
            return self.csharp_analyzer.extract_calls(symbol_node, code)
        elif language in [LanguageEnum.JAVASCRIPT, LanguageEnum.TYPESCRIPT]:
            return self.js_analyzer.extract_calls(symbol_node, code)
        else:
            return []

    async def _extract_usages_for_symbol(
        self,
        symbol_node: "tree_sitter.Node",
        code: str,
        language: LanguageEnum
    ) -> List[Call]:
        """Extract usages from symbol based on language."""
        if language == LanguageEnum.CSHARP:
            return self.csharp_analyzer.extract_usages(symbol_node, code)
        else:
            return []
    
