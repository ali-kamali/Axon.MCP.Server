from typing import List, Dict, Set, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database.models import Symbol, Relation, File
from src.config.enums import RelationTypeEnum, SymbolKindEnum
from src.extractors.call_resolver import CallResolver
from src.parsers.roslyn_integration import RoslynAnalyzer
from src.parsers import ParserFactory
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

class ReferenceBuilder:
    """
    Builds reference relationships from extracted symbol references.
    
    Uses hybrid resolution:
    1. Try Tree-sitter CallResolver first (fast)
    2. If unresolved or low confidence, use Roslyn (accurate)
    """
    
    def __init__(self, session: AsyncSession, use_roslyn: bool = True, roslyn_analyzer: Optional[RoslynAnalyzer] = None):
        self.session = session
        self.resolver = CallResolver(session)
        
        if use_roslyn:
            if roslyn_analyzer:
                # Use shared instance
                self.roslyn = roslyn_analyzer
            else:
                # Create new instance (fallback)
                self.roslyn = RoslynAnalyzer()
        else:
            self.roslyn = None
            
        self.use_roslyn = use_roslyn and (self.roslyn.is_available() if self.roslyn else False)
        
        if self.use_roslyn:
            logger.info("reference_builder_initialized", mode="hybrid")
        else:
            logger.info("reference_builder_initialized", mode="tree_sitter_only")
    
    async def build_all_references(self, repository_id: int) -> int:
        """
        Build references for all files in the repository.
        Reads references from structured_docs (cached during parsing).
        Falls back to re-parsing only if needed.
        Processed in batches to prevent OOM.
        """
        try:
            total_relationships = 0
            files_needing_parse = 0
            
            # 1. Get repository and construct repository path
            from src.database.models import Repository
            from pathlib import Path
            from src.config.settings import get_settings
            from src.config.enums import SourceControlProviderEnum
            
            repo_result = await self.session.execute(
                select(Repository).where(Repository.id == repository_id)
            )
            repo = repo_result.scalar_one_or_none()
            if not repo:
                logger.warning("repository_not_found", repository_id=repository_id)
                return 0
            
            # Construct repository path
            if repo.provider == SourceControlProviderEnum.AZUREDEVOPS:
                repo_path = Path(get_settings().repo_cache_dir).resolve() / "azuredevops" / repo.azuredevops_project_name / repo.name
            elif repo.provider == SourceControlProviderEnum.GITHUB:
                repo_path = Path(get_settings().repo_cache_dir).resolve() / repo.path_with_namespace.replace('/', '_').replace('\\', '_')
            else:
                repo_path = Path(get_settings().repo_cache_dir).resolve() / repo.path_with_namespace.replace('/', '_').replace('\\', '_')
            
            # 2. Get all files for this repository  
            result = await self.session.execute(
                select(File)
                .where(File.repository_id == repository_id)
                .order_by(File.path) # Sort by path for predictable processing
            )
            files = result.scalars().all()
            total_files = len(files)
            
            logger.info("building_all_references_started", total_files=total_files)

            # 3. Process in batches
            BATCH_SIZE = 50 
            for i in range(0, total_files, BATCH_SIZE):
                batch_files = files[i:i + BATCH_SIZE]
                
                # Process each file in batch
                for file in batch_files:
                    try:
                        # Get symbols for this file with their structured_docs
                        symbols_result = await self.session.execute(
                            select(Symbol).where(Symbol.file_id == file.id)
                        )
                        db_symbols = symbols_result.scalars().all()
                        
                        if not db_symbols:
                            continue
                        
                        # Try to use cached references from structured_docs first
                        can_use_cached = all(
                            s.structured_docs and 'references' in s.structured_docs 
                            for s in db_symbols 
                            if s.structured_docs
                        )
                        
                        if can_use_cached:
                            # Fast path: use cached references from database
                            count = await self._build_references_from_db_symbols(
                                repository_id,
                                file,
                                db_symbols,
                                repo_path
                            )
                            total_relationships += count
                        else:
                            # Fallback: re-parse the file
                            files_needing_parse += 1
                            absolute_file_path = repo_path / file.path
                            
                            if not absolute_file_path.exists():
                                logger.debug("file_not_found", file_path=str(absolute_file_path))
                                continue
                            
                            from src.parsers import parse_file_async
                            parse_result = await parse_file_async(absolute_file_path)
                            
                            if parse_result and hasattr(parse_result, 'symbols') and parse_result.symbols:
                                count = await self._build_references_from_parsed_symbols(
                                    repository_id,
                                    file,
                                    parse_result.symbols,
                                    repo_path
                                )
                                total_relationships += count
                            
                    except Exception as e:
                        logger.warning(
                            "file_reference_building_failed",
                            file_path=file.path,
                            error=str(e)
                        )
                        # Continue with next file
                        continue
                
                # Commit and release memory after each batch
                await self.session.commit()
                # Explicitly expunge to free ORM objects
                self.session.expunge_all()
                
                logger.debug(
                    "reference_building_batch_completed", 
                    batch=f"{i//BATCH_SIZE + 1}/{(total_files + BATCH_SIZE - 1)//BATCH_SIZE}",
                    processed=min(i + BATCH_SIZE, total_files),
                    total=total_files
                )

            logger.info(
                "reference_building_summary",
                total_relationships=total_relationships,
                files_needing_parse=files_needing_parse,
                files_using_cache=total_files - files_needing_parse
            )
            return total_relationships

        except Exception as e:
            logger.error("build_all_references_failed", error=str(e))
            raise


    async def _build_references_from_db_symbols(
        self,
        repository_id: int,
        file: File,
        db_symbols: List[Symbol],
        repo_path
    ) -> int:
        """
        Build reference relationships from database symbols using cached references.
        This is the FAST PATH that avoids re-parsing files.
        
        Args:
            repository_id: Repository ID
            file: File record from database
            db_symbols: List of Symbol objects from database with structured_docs
            repo_path: Path to repository root
            
        Returns:
            Number of relationships created
        """
        relationships_created = 0
        
        # Get file content for Roslyn if needed
        file_content = None
        if self.use_roslyn:
            try:
                absolute_file_path = repo_path / file.path
                with open(absolute_file_path, 'r', encoding='utf-8') as f:
                    file_content = f.read()
            except Exception as e:
                logger.warning("failed_to_read_file", file_path=file.path, error=str(e))
                file_content = None
        
        # Pre-fetch imports if possible (simplified for now)
        imports = []
        
        for db_symbol in db_symbols:
            # Get references from structured_docs (cached during initial parsing)
            if not db_symbol.structured_docs or 'references' not in db_symbol.structured_docs:
                continue
            
            references = db_symbol.structured_docs['references']
            if not references:
                continue
                
            # Process each reference
            for ref in references:
                ref_name = ref.get('name')
                ref_type = ref.get('type')
                line = ref.get('line')
                column = ref.get('column')
                
                if not ref_name:
                    continue
                
                # Try Tree-sitter resolution first (fast)
                target_id = await self._resolve_with_tree_sitter(
                    ref_name, db_symbol, file, imports, line, ref_type
                )
                resolved_by_roslyn = False
                
                # If unresolved and Roslyn available, try Roslyn (accurate)
                roslyn_available = self.roslyn and self.roslyn.is_available()
                if not target_id and roslyn_available and file_content:
                    target_id = await self._resolve_with_roslyn(
                        ref_name, file_content, file.path, line, column
                    )
                    resolved_by_roslyn = True if target_id else False
                
                if target_id:
                    # Create REFERENCES relationship
                    relation = Relation(
                        from_symbol_id=db_symbol.id,
                        to_symbol_id=target_id,
                        relation_type=RelationTypeEnum.REFERENCES,
                        relation_metadata={
                            'line': line,
                            'column': column,
                            'ref_type': ref_type,
                            'resolved_by': 'roslyn' if resolved_by_roslyn else 'tree_sitter'
                        }
                    )
                    self.session.add(relation)
                    relationships_created += 1
        
        return relationships_created

    async def _build_references_from_parsed_symbols(
        self,
        repository_id: int,
        file: File,
        parsed_symbols: List,  # These are ParsedSymbol objects from parser
        repo_path
    ) -> int:
        """
        Build reference relationships from freshly parsed symbols.
        
        Args:
            repository_id: Repository ID
            file: File record from database
            parsed_symbols: List of parsed symbols with 'references' attribute
            repo_path: Path to repository root
            
        Returns:
            Number of relationships created
        """
        relationships_created = 0
        
        # Get file content for Roslyn if needed
        file_content = None
        if self.use_roslyn:
            try:
                absolute_file_path = repo_path / file.path
                with open(absolute_file_path, 'r', encoding='utf-8') as f:
                    file_content = f.read()
            except Exception as e:
                logger.warning("failed_to_read_file", file_path=file.path, error=str(e))
                file_content = None
        
        # Pre-fetch imports if possible (simplified for now)
        imports = []
        
        for parsed_symbol in parsed_symbols:
            # Find corresponding database symbol by matching name, kind, and line
            db_symbol = await self._find_db_symbol(file.id, parsed_symbol)
            if not db_symbol:
                logger.debug(
                    "db_symbol_not_found",
                    symbol_name=getattr(parsed_symbol, 'name', 'unknown'),
                    file_path=file.path
                )
                continue
            
            if not hasattr(parsed_symbol, 'references') or not parsed_symbol.references:
                continue
                
            # Process each reference from the parsed symbol
            for ref in parsed_symbol.references:
                ref_name = ref.get('name')
                ref_type = ref.get('type')
                line = ref.get('line')
                column = ref.get('column')
                
                if not ref_name:
                    continue
                
                # Try Tree-sitter resolution first (fast)
                target_id = await self._resolve_with_tree_sitter(
                    ref_name, db_symbol, file, imports, line, ref_type
                )
                resolved_by_roslyn = False
                
                # If unresolved and Roslyn available, try Roslyn (accurate)
                roslyn_available = self.roslyn and self.roslyn.is_available()
                if not target_id and roslyn_available and file_content:
                    target_id = await self._resolve_with_roslyn(
                        ref_name, file_content, file.path, line, column
                    )
                    resolved_by_roslyn = True if target_id else False
                
                if target_id:
                    # Target is guaranteed to exist
                    # Create REFERENCES relationship
                    relation = Relation(
                        from_symbol_id=db_symbol.id,
                        to_symbol_id=target_id,
                        relation_type=RelationTypeEnum.REFERENCES,
                        relation_metadata={
                            'line': line,
                            'column': column,
                            'ref_type': ref_type,
                            'resolved_by': 'roslyn' if resolved_by_roslyn else 'tree_sitter'
                        }
                    )
                    self.session.add(relation)
                    relationships_created += 1
        
        return relationships_created

    async def _find_db_symbol(self, file_id: int, parsed_symbol) -> Optional[Symbol]:
        """
        Find database symbol matching the parsed symbol.
        
        Args:
            file_id: File ID 
            parsed_symbol: Parsed symbol with name, kind, start_line
            
        Returns:
            Matching Symbol from database or None
        """
        try:
            # Match by file, name, kind, and line number
            name = getattr(parsed_symbol, 'name', None)
            kind = getattr(parsed_symbol, 'kind', None)
            start_line = getattr(parsed_symbol, 'start_line', None)
            
            if not name or not kind or not start_line:
                return None
            
            result = await self.session.execute(
                select(Symbol).where(
                    Symbol.file_id == file_id,
                    Symbol.name == name,
                    Symbol.kind == kind,
                    Symbol.start_line == start_line
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.debug("find_db_symbol_failed", error=str(e))
            return None

    
    async def _resolve_with_tree_sitter(
        self,
        ref_name: str,
        symbol: Symbol,
        file: File,
        imports: List[str],
        line: int,
        ref_type: Optional[str] = None
    ) -> Optional[int]:
        """
        Resolve reference using Tree-sitter CallResolver.
        
        Returns:
            Symbol ID if resolved, None otherwise
        """
        try:
            # If it's a type reference, use resolve_type
            if ref_type in ['instantiation', 'type_reference', 'type_argument', 'cast', 'di_registration']:
                return await self.resolver.resolve_type(
                    ref_name,
                    file,
                    imports
                )

            # Otherwise, assume it's a method call (fallback)
            # Mock a "Call" object since CallResolver expects it
            from src.extractors.call_analyzer import Call
            mock_call = Call(
                method_name=ref_name,
                receiver=None,
                arguments=[],
                line_number=line,
                end_line=line,
                start_column=0,
                end_column=0
            )
            
            return await self.resolver.resolve_call_target(
                mock_call,
                symbol,
                file,
                imports
            )
        except Exception as e:
            logger.debug("tree_sitter_resolution_failed", ref_name=ref_name, error=str(e))
            return None

    async def _resolve_with_roslyn(
        self,
        ref_name: str,
        file_content: str,
        file_path: str,
        line: int,
        column: int
    ) -> Optional[int]:
        """
        Resolve reference using Roslyn semantic analysis.
        
        Args:
            ref_name: Reference name
            file_content: Full file content
            file_path: Path to file
            line: Line number
            column: Column number
            
        Returns:
            Symbol ID if resolved, None otherwise
        """
        try:
            # Calculate character position from line/column
            lines = file_content.split('\n')
            position = sum(len(l) + 1 for l in lines[:line-1]) + column
            
            # Use Roslyn to resolve reference
            result = await self.roslyn.resolve_reference(
                file_content,
                file_path,
                position
            )
            
            if not result:
                return None
            
            # Look up symbol by fully qualified name
            fqn = result.get('fully_qualified_name')
            if not fqn:
                return None
            
            # Query database for symbol with this FQN
            query = select(Symbol).where(Symbol.fully_qualified_name == fqn)
            db_result = await self.session.execute(query)
            target_symbol = db_result.scalar_one_or_none()
            
            if target_symbol:
                logger.debug(
                    "roslyn_resolved_reference",
                    ref_name=ref_name,
                    fqn=fqn,
                    target_id=target_symbol.id
                )
                return target_symbol.id
            else:
                logger.debug("roslyn_symbol_not_in_db", fqn=fqn)
                return None
                
        except Exception as e:
            logger.debug("roslyn_resolution_failed", ref_name=ref_name, error=str(e))
            return None
    
