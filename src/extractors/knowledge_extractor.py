from typing import List, Dict, Optional, Set, Tuple, Any
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from src.database.models import Symbol, Relation, File, Chunk, Dependency, Solution, Project, ProjectReference, Repository
from src.parsers.base_parser import ParseResult, ParsedSymbol
from src.config.enums import SymbolKindEnum, RelationTypeEnum, LanguageEnum
from src.utils.logging_config import get_logger
from src.utils.async_compat import maybe_await
from src.utils.data_validation import truncate_string
from src.embeddings.symbol_chunker import SymbolChunker, ChunkConfig
from src.embeddings.chunk_context import ChunkContextBuilder
from src.extractors.relationship_builder import RelationshipBuilder

from src.extractors.project_resolver import ProjectResolver
from src.analyzers.service_boundary_analyzer import ServiceBoundaryAnalyzer
import hashlib
import json
from pathlib import Path

logger = get_logger(__name__)



@dataclass
class ExtractionResult:
    """Result of knowledge extraction."""
    symbols_created: int
    symbols_updated: int
    relations_created: int
    chunks_created: int
    dependencies_created: int
    solutions_created: int = 0
    projects_created: int = 0
    project_refs_created: int = 0
    errors: List[str] = None
    
    def __post_init__(self):
        """Initialize mutable defaults."""
        if self.errors is None:
            self.errors = []

class KnowledgeExtractor:
    """Extracts and persists structured knowledge from parse results."""
    
    def __init__(self, session: AsyncSession):
        """
        Initialize knowledge extractor.
        
        Args:
            session: Database session
        """
        self.session = session
        self.chunker = SymbolChunker(ChunkConfig())
        self.context_builder = ChunkContextBuilder(session)
        self.project_resolver = ProjectResolver(session)
        self.service_analyzer = ServiceBoundaryAnalyzer()
    
    async def extract_and_persist(
        self,
        parse_result: ParseResult,
        file_id: int,
        commit_id: Optional[int] = None
    ) -> ExtractionResult:
        """
        Extract knowledge from parse result and persist to database.
        
        Args:
            parse_result: Parsed code result
            file_id: Database file ID
            commit_id: Optional commit ID
            
        Returns:
            ExtractionResult with statistics
        """
        symbols_created = 0
        symbols_updated = 0
        relations_created = 0
        chunks_created = 0
        dependencies_created = 0
        errors = []
        
        try:
            # Get file info for project resolution
            result = await self.session.execute(
                select(File).where(File.id == file_id)
            )
            file_obj = result.scalar_one_or_none()
            repo_id = file_obj.repository_id if file_obj else None
            file_path = file_obj.path if file_obj else parse_result.file_path
            
            # Resolve project (Phase 2.2)
            project_id = None
            assembly_name = None
            if repo_id and file_path:
                project_id = await self.project_resolver.get_project_for_file(file_path, repo_id)
                if project_id:
                    project_meta = await self.project_resolver.get_project_metadata(project_id)
                    if project_meta:
                        assembly_name = project_meta.get('assembly_name')
            
            # Cache existing AI enrichment before deletion
            existing_enrichment_map = {}
            try:
                # Query existing symbols with enrichment for this file
                enrichment_query = select(Symbol.fully_qualified_name, Symbol.name, Symbol.ai_enrichment).where(
                    Symbol.file_id == file_id,
                    Symbol.ai_enrichment.isnot(None)
                )
                result = await self.session.execute(enrichment_query)
                for fqn, name, enrichment in result.all():
                    # Key by fully_qualified_name (primary) or name (fallback)
                    # For methods, FQN is safer.
                    key = fqn or name
                    if key:
                        existing_enrichment_map[key] = enrichment
                
                if existing_enrichment_map:
                    logger.info("cached_enrichment_for_preservation", file_id=file_id, count=len(existing_enrichment_map))
            except Exception as e:
                logger.warning("failed_to_cache_enrichment", error=str(e))

            # Delete existing symbols and dependencies for this file (for re-parsing)
            await self.session.execute(
                delete(Symbol).where(Symbol.file_id == file_id)
            )
            await self.session.execute(
                delete(Dependency).where(Dependency.file_id == file_id)
            )
            
            # Create symbol map for relationship building
            symbol_map: Dict[str, int] = {}
            created_symbols: List[Symbol] = []  # Track created symbols for ReferenceBuilder
            
            # Persist symbols
            for parsed_symbol in parse_result.symbols:
                try:
                    symbol = await self._create_symbol(
                        parsed_symbol,
                        file_id,
                        commit_id,
                        parse_result.language,
                        project_id,
                        assembly_name
                    )
                    
                    # Restore enrichment if available
                    key = parsed_symbol.fully_qualified_name or parsed_symbol.name
                    if key and key in existing_enrichment_map:
                        symbol.ai_enrichment = existing_enrichment_map[key]
                        # Track that we restored it (optional, for debugging/metrics)
                        # symbol.enrichment_status = "restored"  # If we had such a field

                    # PHASE 1: Eager parent linking (if parent already created)
                    if parsed_symbol.parent_name and parsed_symbol.parent_name in symbol_map:
                        symbol.parent_symbol_id = symbol_map[parsed_symbol.parent_name]

                    await maybe_await(self.session.add(symbol))
                    await self.session.flush()  # Get ID
                    
                    symbol_map[parsed_symbol.fully_qualified_name or parsed_symbol.name] = symbol.id
                    created_symbols.append(symbol)  # Track for ReferenceBuilder
                    symbols_created += 1
                    
                    # Create chunks for symbol using new symbol-based chunker
                    chunks = await self._create_chunks_for_symbol(symbol, parsed_symbol, file_id)
                    for chunk in chunks:
                        await maybe_await(self.session.add(chunk))
                        chunks_created += 1
                    
                    # Flush chunks immediately to ensure FK constraint validation happens now
                    # This prevents deferred constraint violations from corrupting the session
                    if chunks:
                        await self.session.flush()
                    
                except Exception as e:
                    error_msg = f"Failed to create symbol: {str(e)}"
                    logger.error(
                        "symbol_creation_failed",
                        symbol_name=parsed_symbol.name,
                        error=error_msg
                    )
                    errors.append(f"Symbol {parsed_symbol.name}: {error_msg}")
                    
                    # Roll back the session to clear the failed transaction
                    # This prevents PendingRollbackError on subsequent operations
                    await self.session.rollback()
                    
                    # Remove the failed symbol from tracking if it was added
                    # Note: symbol may not exist if error occurred in _create_symbol
                    symbol_key = parsed_symbol.fully_qualified_name or parsed_symbol.name
                    if symbol_key in symbol_map:
                        del symbol_map[symbol_key]
                    try:
                        if 'symbol' in locals() and symbol in created_symbols:
                            created_symbols.remove(symbol)
                    except (NameError, UnboundLocalError):
                        pass  # symbol was never created
            
            # PHASE 2: Cleanup pass - fix remaining NULL parent_symbol_id
            # This catches cases where child was created before parent in parse order
            for symbol in created_symbols:
                if not symbol.parent_symbol_id and symbol.parent_name:
                    # Try to resolve parent from symbol_map
                    parent_id = symbol_map.get(symbol.parent_name)
                    if parent_id:
                        symbol.parent_symbol_id = parent_id
                        logger.debug(
                            "parent_link_resolved_cleanup",
                            symbol=symbol.name,
                            parent=symbol.parent_name
                        )
            
            # Build and persist parent-child relationships (CONTAINS relations)
            relations = await self._build_relationships(parse_result, symbol_map, file_id)
            for relation in relations:
                await maybe_await(self.session.add(relation))
                relations_created += 1
            
            # Process nested lambdas (Phase 3.1)
            # We need to iterate over a copy of created symbols because we might append new ones
            # But actually, lambdas are inside structured_docs of the parent symbol
            # We should extract them and create symbols for them
            
            # Collect lambdas from created symbols
            lambda_symbols_to_create = []
            for parent_symbol in created_symbols:
                if parent_symbol.structured_docs and 'lambdas' in parent_symbol.structured_docs:
                    lambdas_data = parent_symbol.structured_docs['lambdas']
                    # These are now dictionaries, not ParsedSymbol objects
                    for lambda_dict in lambdas_data:
                        if isinstance(lambda_dict, dict):
                            # Reconstruct ParsedSymbol from dictionary
                            lambda_parsed = ParsedSymbol(
                                kind=SymbolKindEnum.METHOD,
                                name=lambda_dict['name'],
                                fully_qualified_name=lambda_dict['fully_qualified_name'],
                                start_line=lambda_dict['start_line'],
                                end_line=lambda_dict['end_line'],
                                start_column=lambda_dict.get('start_column', 0),
                                end_column=lambda_dict.get('end_column', 0),
                                signature=lambda_dict['signature'],
                                parameters=lambda_dict['parameters'],
                                structured_docs={
                                    'is_lambda': True,
                                    'closure_variables': lambda_dict.get('closure_variables'),
                                    'linq_pattern': lambda_dict.get('linq_pattern')
                                }
                            )
                            lambda_symbols_to_create.append((lambda_parsed, parent_symbol))
            
            # Create lambda symbols
            for lambda_parsed, parent_symbol in lambda_symbols_to_create:
                try:
                    # Link to parent
                    lambda_parsed.parent_symbol_id = parent_symbol.id
                    
                    l_symbol = await self._create_symbol(
                        lambda_parsed,
                        file_id,
                        commit_id,
                        parse_result.language,
                        project_id,
                        assembly_name
                    )
                    
                    # Restore enrichment for lambda if available
                    key = lambda_parsed.fully_qualified_name or lambda_parsed.name
                    if key and key in existing_enrichment_map:
                        l_symbol.ai_enrichment = existing_enrichment_map[key]

                    l_symbol.parent_symbol_id = parent_symbol.id # Ensure link
                    
                    await maybe_await(self.session.add(l_symbol))
                    await self.session.flush()
                    
                    symbol_map[lambda_parsed.fully_qualified_name] = l_symbol.id
                    created_symbols.append(l_symbol)
                    symbols_created += 1
                    
                    # Create chunks for lambda
                    chunks = await self._create_chunks_for_symbol(l_symbol, lambda_parsed, file_id)
                    for chunk in chunks:
                        await maybe_await(self.session.add(chunk))
                        chunks_created += 1
                    
                    # Flush chunks immediately to ensure FK constraint validation happens now
                    if chunks:
                        await self.session.flush()
                        
                except Exception as e:
                    logger.error(
                        "lambda_creation_failed",
                        parent_symbol=parent_symbol.name,
                        error=str(e)
                    )
                    
                    # Roll back the session to clear the failed transaction
                    await self.session.rollback()
                    
                    # Remove the failed lambda from tracking if it was added
                    try:
                        if 'l_symbol' in locals():
                            lambda_key = lambda_parsed.fully_qualified_name
                            if lambda_key in symbol_map:
                                del symbol_map[lambda_key]
                            if l_symbol in created_symbols:
                                created_symbols.remove(l_symbol)
                    except (NameError, UnboundLocalError):
                        pass  # l_symbol was never created
            

            
            # Create dependencies
            dependencies = await self._create_dependencies(parse_result, file_id)
            # Create project references
            project_refs_created = await self._create_project_references(parse_result, file_id)
            # Create solutions and projects
            solutions_created, projects_created = await self._create_solutions_and_projects(parse_result, file_id)
            
            # Merge partial classes (Phase 2.1)
            await self._merge_partial_classes(file_id, created_symbols)
            
            # Service Detection is now handled once at the end of repository sync
            # in sync_worker.py, after all symbols and relationships are committed.
            # This ensures controllers are visible and prevents duplicate detection.
            # 
            # Previous per-file approach (DEPRECATED):
            # if repo_id and (file_path.endswith('.csproj') or file_path.endswith('package.json')):
            #     repo = await self.session.get(Repository, repo_id)
            #     if repo:
            #         services = await self.service_analyzer.detect_services(repo, self.session)
            #         for service in services:
            #             self.session.add(service)
            #         await self.session.flush()
            
            
            logger.info(
                "knowledge_extraction_completed",
                file_id=file_id,
                symbols=symbols_created,
                relations=relations_created,
                chunks=chunks_created,
                dependencies=dependencies_created,
                solutions=solutions_created,
                projects=projects_created,
                project_refs=project_refs_created
            )
            
        except Exception as e:
            error_msg = f"Failed to extract knowledge: {str(e)}"
            logger.error("knowledge_extraction_failed", file_id=file_id, error=error_msg)
            errors.append(error_msg)
            raise
        
        return ExtractionResult(
            symbols_created=symbols_created,
            symbols_updated=symbols_updated,
            relations_created=relations_created,
            chunks_created=chunks_created,
            dependencies_created=dependencies_created,
            solutions_created=solutions_created,
            projects_created=projects_created,
            project_refs_created=project_refs_created,
            errors=errors
        )
    
    async def _create_symbol(
        self,
        parsed: ParsedSymbol,
        file_id: int,
        commit_id: Optional[int],
        language: LanguageEnum,
        project_id: Optional[int] = None,
        assembly_name: Optional[str] = None
    ) -> Symbol:
        """Create Symbol database model from parsed symbol."""
        # Calculate complexity (use parser's calculation if available, defaulting to 1 in ParsedSymbol)
        complexity = parsed.complexity
        
        # If parser didn't calculate it (still 1) and we have parameters, maybe boost it slightly?
        # But for now, trust the parser or the default. 
        # Actually, let's keep the parameter heuristic if parser returned default 1 
        # to ensure at least some differentiation for methods with many params.
        if complexity == 1 and parsed.parameters:
            complexity += len(parsed.parameters)
        
        # Safely truncate string fields to prevent database errors
        # Max lengths based on database schema: name=1000, fully_qualified_name=2000, return_type=1000
        fully_qualified_name = truncate_string(
            parsed.fully_qualified_name or parsed.name,
            2000,
            "symbol.fully_qualified_name"
        )
        return_type = truncate_string(parsed.return_type, 1000, "symbol.return_type")
        
        symbol = Symbol(
            file_id=file_id,
            commit_id=commit_id,
            project_id=project_id,
            assembly_name=assembly_name,
            language=language,
            kind=parsed.kind,
            access_modifier=parsed.access_modifier,
            name=parsed.name,
            fully_qualified_name=fully_qualified_name,
            parent_name=parsed.parent_name,
            start_line=parsed.start_line,
            end_line=parsed.end_line,
            start_column=parsed.start_column,
            end_column=parsed.end_column,
            signature=parsed.signature,
            documentation=parsed.documentation,
            structured_docs=parsed.structured_docs,
            attributes=self._extract_attributes_from_structured_docs(parsed.structured_docs),
            parameters=parsed.parameters,
            return_type=return_type,
            complexity=complexity,
            complexity_score=complexity,
            token_count=len(parsed.signature.split()) if parsed.signature else 0,
            generic_parameters=parsed.generic_parameters,
            constraints=parsed.constraints,
            is_partial=1 if parsed.structured_docs and parsed.structured_docs.get('is_partial') else 0,
            
            # Phase 3.1: Lambda Analysis
            is_lambda=1 if parsed.structured_docs and parsed.structured_docs.get('is_lambda') else 0,
            closure_variables=parsed.structured_docs.get('closure_variables') if parsed.structured_docs else None,
            linq_pattern=parsed.structured_docs.get('linq_pattern') if parsed.structured_docs else None
        )
        
        # Persist references in structured_docs (Phase 3.5 Fix)
        # This allows RelationshipBuilder to access rich usage data (DI, vars, etc.)
        if parsed.references:
            if symbol.structured_docs is None:
                symbol.structured_docs = {}
            # Use strict assignment to ensure valid JSON serialization later
            symbol.structured_docs['references'] = [dict(r) for r in parsed.references]
        
        # Temporarily attach references for ReferenceBuilder (not stored in DB column)
        symbol.references = parsed.references
        
        return symbol
    
    async def _create_chunks_for_symbol(
        self,
        symbol: Symbol,
        parsed: ParsedSymbol,
        file_id: int
    ) -> List[Chunk]:
        """
        Create rich chunks for symbol using new SymbolChunker.
        
        This replaces the old simple chunking with context-aware chunking.
        """
        chunks = []
        
        # Get file for context
        result = await self.session.execute(
            select(File).where(File.id == file_id)
        )
        file = result.scalar_one_or_none()
        if not file:
            # Fallback to old method if file not found
            return await self._create_chunk_legacy(symbol, parsed, file_id)
        
        try:
            # Build rich context for symbol
            context = await self.context_builder.build_context(symbol, file)
            
            # Create chunks using SymbolChunker
            # Some tests use async test doubles for this method; support both sync and async implementations.
            chunk_dicts = await maybe_await(
                self.chunker.create_chunks_for_symbol(
                    symbol, file, context, file_content=None  # Could load file content here
                )
            )
            
            # Convert chunk dicts to Chunk models
            for chunk_dict in chunk_dicts:
                content = chunk_dict['content']
                content_hash = hashlib.sha256(content.encode()).hexdigest()
                
                chunk = Chunk(
                    file_id=file_id,
                    symbol_id=symbol.id,
                    content=content,
                    content_type=chunk_dict['content_type'],
                    chunk_subtype=chunk_dict.get('chunk_subtype'),
                    context_metadata=chunk_dict.get('context_metadata'),
                    token_count=len(content.split()),
                    start_line=chunk_dict.get('start_line', parsed.start_line),
                    end_line=chunk_dict.get('end_line', parsed.end_line),
                    content_hash=content_hash
                )
                chunks.append(chunk)
            
        except Exception as e:
            logger.warning(
                "symbol_chunking_failed_fallback",
                symbol_id=symbol.id,
                error=str(e)
            )
            # Fallback to legacy chunking on error
            legacy_chunks = await self._create_chunk_legacy(symbol, parsed, file_id)
            chunks.extend(legacy_chunks)
        
        return chunks
    
    async def _create_chunk_legacy(
        self,
        symbol: Symbol,
        parsed: ParsedSymbol,
        file_id: int
    ) -> List[Chunk]:
        """
        Legacy chunk creation for backward compatibility.
        
        This is the old simple method, kept as fallback.
        """
        # Create searchable text combining signature and documentation
        content_parts = []
        
        if parsed.signature:
            content_parts.append(parsed.signature)
        
        if parsed.documentation:
            content_parts.append(parsed.documentation)
        
        if not content_parts:
            return []
        
        content = "\n\n".join(content_parts)
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        
        chunk = Chunk(
            file_id=file_id,
            symbol_id=symbol.id,
            content=content,
            content_type="signature_with_docs",
            token_count=len(content.split()),
            start_line=parsed.start_line,
            end_line=parsed.end_line,
            content_hash=content_hash
        )
        
        return [chunk]
    
    async def _build_relationships(
        self,
        parse_result: ParseResult,
        symbol_map: Dict[str, int],
        file_id: int
    ) -> List[Relation]:
        """Build relationships between symbols."""
        relations = []
        
        # Parent-child relationships (contains)
        for parsed in parse_result.symbols:
            if parsed.parent_name and parsed.parent_name in symbol_map:
                parent_id = symbol_map[parsed.parent_name]
                child_fqn = parsed.fully_qualified_name or parsed.name
                
                if child_fqn in symbol_map:
                    child_id = symbol_map[child_fqn]
                    
                    relations.append(Relation(
                        from_symbol_id=parent_id,
                        to_symbol_id=child_id,
                        relation_type=RelationTypeEnum.CONTAINS
                    ))
        
        # Import relationships (simplified - would need cross-file analysis)
        # This would be enhanced in a real implementation with cross-file resolution
        
        return relations
    
    def _calculate_complexity(self, parsed: ParsedSymbol) -> int:
        """Calculate symbol complexity (simplified)."""
        if parsed.kind in [SymbolKindEnum.FUNCTION, SymbolKindEnum.METHOD]:
            # Base complexity
            complexity = 1
            
            # Add complexity for parameters
            if parsed.parameters:
                complexity += len(parsed.parameters)
            
            # Could analyze signature for conditional statements, loops, etc.
            # This is a placeholder for more sophisticated analysis
            
            return complexity
        
        return 0
    
    def _extract_attributes_from_structured_docs(self, structured_docs: Optional[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """
        Extract attributes list from structured_docs.
        
        Args:
            structured_docs: Dictionary containing structured documentation, may include 'attributes' key
            
        Returns:
            List of attribute dictionaries if found, None otherwise
        """
        if not structured_docs:
            return None
        
        return structured_docs.get('attributes')
    
    def _normalize_guid(self, guid: Optional[str]) -> Optional[str]:
        """
        Normalize GUID by stripping curly braces.
        
        GUIDs in .sln files are often stored with curly braces like {7A7162AB-6732-4B7C-A061-30C3A47EB6B6},
        but the database field is VARCHAR(36) which expects the format without braces.
        
        Args:
            guid: GUID string, possibly with curly braces
            
        Returns:
            GUID without curly braces, or None if input is None
        """
        if not guid:
            return None
        
        # Strip curly braces if present
        normalized = guid.strip('{}')
        
        return normalized
    
    def _normalize_project_path(
        self,
        project_path: str,
        file_path: Optional[str] = None
    ) -> str:
        r"""
        Normalize project path.
        
        Project paths from .sln files are relative (e.g., "Axon.Health.Api\Axon.Health.Api.csproj"),
        while project paths from .csproj parsing are absolute.
        
        This method converts relative paths to normalized paths by resolving them relative to the
        solution file directory, but keeping them relative to the repository root if possible.
        
        Args:
            project_path: Project path (may be relative or absolute)
            file_path: Solution file path (for resolving relative paths)
            
        Returns:
            Normalized path
        """
        from pathlib import Path
        import os
        
        # Already absolute
        if Path(project_path).is_absolute():
            return str(Path(project_path).as_posix())
        
        # Relative path - need solution directory
        if not file_path:
            # Can't resolve without solution path, return as-is
            return project_path
        
        # Get solution directory
        solution_dir = Path(file_path).parent
        
        # Resolve relative to solution directory
        # Handle both forward and backslash separators
        project_path_normalized = project_path.replace('\\', '/')
        
        # Use os.path.normpath to resolve '..' but keep it relative if solution_dir is relative
        # We avoid .resolve() because it makes paths absolute based on current working directory
        combined_path = solution_dir / project_path_normalized
        normalized_path = os.path.normpath(str(combined_path))
        
        # Convert back to posix style (forward slashes) for consistency
        return normalized_path.replace('\\', '/')
    
    async def _find_existing_project(
        self,
        name: str,
        repository_id: int,
        file_path: str,
        project_guid: Optional[str] = None
    ) -> Optional[Project]:
        """
        Find existing project using multiple matching strategies.
        
        Strategies (in order):
        1. Exact file_path match
        2. Match by project_guid (if provided)
        3. Match by name + repository_id (fallback for orphaned projects)
        
        Args:
            name: Project name
            repository_id: Repository ID
            file_path: Project file path (should be normalized)
            project_guid: Optional project GUID
            
        Returns:
            Existing Project or None
        """
        # Strategy 1: Exact file path match
        stmt = select(Project).where(
            Project.repository_id == repository_id,
            Project.file_path == file_path
        )
        result = await self.session.execute(stmt)
        project = result.scalar_one_or_none()
        if project:
            logger.debug("project_found_by_path", name=name, file_path=file_path)
            return project
        
        # Strategy 2: Match by project_guid (if provided and valid)
        if project_guid and project_guid.strip():
            stmt = select(Project).where(
                Project.repository_id == repository_id,
                Project.project_guid == project_guid
            )
            result = await self.session.execute(stmt)
            project = result.scalar_one_or_none()
            if project:
                logger.debug("project_found_by_guid", name=name, guid=project_guid)
                return project
        
        # Strategy 3: Match by name + path suffix (handle absolute vs relative mismatch)
        # This handles the case where DB has absolute path but we now have relative path (or vice versa)
        # We query by name first to limit candidates
        stmt = select(Project).where(
            Project.repository_id == repository_id,
            Project.name == name
        )
        result = await self.session.execute(stmt)
        candidates = result.scalars().all()
        
        for candidate in candidates:
            # Check if paths match (ignoring absolute/relative difference)
            # Use simple string suffix matching which is robust for "src/A/A.csproj" vs "/app/src/A/A.csproj"
            # We check both directions to be safe
            if candidate.file_path.endswith(file_path) or file_path.endswith(candidate.file_path):
                 logger.info(
                     "project_found_by_path_suffix", 
                     name=name, 
                     existing_path=candidate.file_path, 
                     new_path=file_path
                 )
                 return candidate

        # Strategy 4: Match by name + repository (fallback for orphaned projects)
        # Only match if the existing project has null solution_id and project_guid
        # This is for when we really can't match the path (e.g. moved file)
        stmt = select(Project).where(
            Project.repository_id == repository_id,
            Project.name == name,
            Project.solution_id == None,
            Project.project_guid == None
        )
        result = await self.session.execute(stmt)
        project = result.scalar_one_or_none()
        if project:
            logger.info(
                "project_found_orphan_by_name",
                name=name,
                existing_path=project.file_path,
                new_path=file_path
            )
            return project
        
        return None

    async def _create_dependencies(
        self,
        parse_result: ParseResult,
        file_id: int
    ) -> List[Dependency]:
        """Create Dependency database models from parsed symbols."""
        dependencies = []
        
        # Get repository_id from file
        result = await self.session.execute(
            select(File.repository_id).where(File.id == file_id)
        )
        repository_id = result.scalar_one_or_none()
        
        if not repository_id:
            logger.warning("file_not_found_for_dependency", file_id=file_id)
            return []
            
        for parsed in parse_result.symbols:
            # Check if symbol represents a dependency
            if not parsed.structured_docs:
                continue
                
            doc_type = parsed.structured_docs.get('type')
            
            if doc_type in ['npm_package', 'nuget_package']:
                # Extract dependency info
                package_name = parsed.name
                package_version = parsed.structured_docs.get('version')
                is_dev = parsed.structured_docs.get('is_dev_dependency', False)
                
                # Determine dependency type
                dep_type = 'npm' if doc_type == 'npm_package' else 'nuget'
                
                # Extract additional fields
                version_constraint = package_version  # Usually the version string is the constraint
                
                dependencies.append(Dependency(
                    repository_id=repository_id,
                    file_id=file_id,
                    package_name=package_name,
                    package_version=package_version,
                    version_constraint=version_constraint,
                    dependency_type=dep_type,
                    is_dev_dependency=1 if is_dev else 0,
                    is_transitive=0,  # Parsers currently only find direct dependencies
                    file_path=parse_result.file_path
                ))
                
                
        return dependencies

    async def _create_project_references(
        self,
        parse_result: ParseResult,
        file_id: int
    ) -> int:
        """
        Create ProjectReference database models from parsed symbols.
        
        Args:
            parse_result: Parsed code result
            file_id: Database file ID
            
        Returns:
            Count of project references created
        """
        project_references_created = 0
        
        # Get repository_id and source project path from file
        result = await self.session.execute(
            select(File.repository_id, File.path).where(File.id == file_id)
        )
        row = result.one_or_none()
        if not row:
            logger.warning("file_not_found_for_project_reference", file_id=file_id)
            return 0
        
        repository_id, source_project_path = row
        
        # Normalize source path
        source_project_path_normalized = self._normalize_project_path(source_project_path)
        
        # Delete existing project references for this file (for re-parsing)
        await self.session.execute(
            delete(ProjectReference).where(
                ProjectReference.repository_id == repository_id,
                ProjectReference.source_project_path == source_project_path_normalized
            )
        )
        
        # Extract project references from parsed symbols
        for parsed in parse_result.symbols:
            if not parsed.structured_docs:
                continue
            
            doc_type = parsed.structured_docs.get('type')
            
            if doc_type == 'project_reference':
                # Get target project path (relative from .csproj)
                target_path = parsed.structured_docs.get('path')
                if not target_path:
                    logger.warning(
                        "project_reference_missing_path",
                        file_id=file_id,
                        name=parsed.name
                    )
                    continue
                
                # Normalize target path (resolve relative to source project directory)
                # The target path is relative to the source .csproj file
                target_project_path = self._normalize_project_path(
                    target_path,
                    source_project_path
                )
                
                project_ref = ProjectReference(
                    repository_id=repository_id,
                    source_project_path=source_project_path_normalized,
                    target_project_path=target_project_path,
                    reference_type='project'
                )
                
                await maybe_await(self.session.add(project_ref))
                project_references_created += 1
                
                logger.debug(
                    "project_reference_created",
                    source=source_project_path_normalized,
                    target=target_project_path
                )
        
        return project_references_created

    async def _create_solutions_and_projects(
        self,
        parse_result: ParseResult,
        file_id: int
    ) -> Tuple[int, int]:
        """
        Create Solution and Project database models from parsed symbols.
        
        Returns:
            Tuple of (solutions_created, projects_created)
        """
        solutions_created = 0
        projects_created = 0
        
        # Get repository_id from file
        result = await self.session.execute(
            select(File.repository_id).where(File.id == file_id)
        )
        repository_id = result.scalar_one_or_none()
        
        if not repository_id:
            return 0, 0
            
        # Check if this is a solution file
        if parse_result.file_path.endswith('.sln'):
            # Find solution symbol
            solution_symbol = next(
                (s for s in parse_result.symbols if s.structured_docs and s.structured_docs.get('type') == 'solution'),
                None
            )
            
            if solution_symbol:
                # Create Solution
                docs = solution_symbol.structured_docs
                solution = Solution(
                    repository_id=repository_id,
                    file_path=parse_result.file_path,
                    name=solution_symbol.name,
                    format_version=docs.get('format_version'),
                    visual_studio_version=docs.get('visual_studio_version'),
                    visual_studio_full_version=docs.get('visual_studio_full_version'),
                    minimum_visual_studio_version=docs.get('minimum_visual_studio_version')
                )
                await maybe_await(self.session.add(solution))
                await self.session.flush()  # Get ID
                solutions_created += 1
                
                # Create Projects linked to this solution
                for symbol in parse_result.symbols:
                    if symbol.structured_docs and symbol.structured_docs.get('type') == 'project':
                        p_docs = symbol.structured_docs
                        
                        # Validate required fields (name and file_path are NOT NULL in database)
                        project_name = p_docs.get('project_name')
                        project_path = p_docs.get('project_path')
                        
                        if not project_name or not project_path:
                            logger.warning(
                                "project_missing_required_fields",
                                project_name=project_name,
                                project_path=project_path,
                                file_id=file_id
                            )
                            continue
                        
                        # Normalize project path (convert relative to absolute)
                        normalized_project_path = self._normalize_project_path(project_path, parse_result.file_path)
                        
                        # Normalize GUIDs by stripping curly braces
                        project_guid = self._normalize_guid(p_docs.get('project_guid'))
                        project_type_guid = self._normalize_guid(p_docs.get('project_type_guid'))
                        
                        # Check if project already exists (prevent duplicates)
                        existing_project = await self._find_existing_project(
                            name=project_name,
                            repository_id=repository_id,
                            file_path=normalized_project_path,
                            project_guid=project_guid
                        )
                        
                        if existing_project:
                            # Update existing project with solution metadata
                            existing_project.solution_id = solution.id
                            existing_project.project_guid = truncate_string(project_guid, 36, "project.project_guid")
                            existing_project.project_type = truncate_string(p_docs.get('project_type'), 100, "project.project_type")
                            existing_project.project_type_guid = truncate_string(project_type_guid, 36, "project.project_type_guid")
                            existing_project.file_path = truncate_string(normalized_project_path, 1000, "project.file_path")
                            await maybe_await(self.session.add(existing_project))
                            logger.info(
                                "project_updated_with_solution_metadata",
                                project_id=existing_project.id,
                                name=project_name,
                                solution_id=solution.id
                            )
                        else:
                            # Create new project
                            project = Project(
                                repository_id=repository_id,
                                solution_id=solution.id,
                                project_guid=truncate_string(project_guid, 36, "project.project_guid"),
                                name=truncate_string(project_name, 255, "project.name"),
                                file_path=truncate_string(normalized_project_path, 1000, "project.file_path"),
                                project_type=truncate_string(p_docs.get('project_type'), 100, "project.project_type"),
                                project_type_guid=truncate_string(project_type_guid, 36, "project.project_type_guid")
                            )
                            await maybe_await(self.session.add(project))
                            projects_created += 1
        
        # Check if this is a project file (.csproj)
        elif parse_result.file_path.endswith('.csproj'):
            # Find project metadata symbol
            metadata_symbol = next(
                (s for s in parse_result.symbols 
                 if s.structured_docs and s.structured_docs.get('type') == 'project_metadata'),
                None
            )
            
            if metadata_symbol and metadata_symbol.structured_docs:
                docs = metadata_symbol.structured_docs
                name = Path(parse_result.file_path).stem
                
                # Normalize path
                normalized_path = self._normalize_project_path(parse_result.file_path)
                
                # Find existing project using smart matching
                project = await self._find_existing_project(
                    name=name,
                    repository_id=repository_id,
                    file_path=normalized_path,
                    project_guid=None
                )
                
                if project:
                    # Update existing project with .csproj metadata
                    project.target_framework = docs.get('target_framework')
                    project.output_type = docs.get('output_type')
                    project.assembly_name = docs.get('assembly_name')
                    project.root_namespace = docs.get('root_namespace')
                    project.define_constants = docs.get('define_constants')
                    project.lang_version = docs.get('lang_version')
                    project.nullable_context = docs.get('nullable')
                    project.file_path = truncate_string(normalized_path, 1000, "project.file_path")  # Update to normalized path
                    
                    await maybe_await(self.session.add(project))
                    logger.info(
                        "project_updated_with_csproj_metadata",
                        project_id=project.id,
                        name=name
                    )
                else:
                    # Create new project (orphan, no solution yet)
                    project = Project(
                        repository_id=repository_id,
                        name=name,
                        file_path=truncate_string(normalized_path, 1000, "project.file_path"),
                        project_type="C# Project",  # Default
                        target_framework=docs.get('target_framework'),
                        output_type=docs.get('output_type'),
                        assembly_name=docs.get('assembly_name'),
                        root_namespace=docs.get('root_namespace'),
                        define_constants=docs.get('define_constants'),
                        lang_version=docs.get('lang_version'),
                        nullable_context=docs.get('nullable')
                    )
                    await maybe_await(self.session.add(project))
                    projects_created += 1
                    logger.info(
                        "project_created_from_csproj",
                        name=name,
                        file_path=normalized_path
                    )
            
        return solutions_created, projects_created

    async def _merge_partial_classes(self, file_id: int, created_symbols: List[Symbol]):
        """
        Merge partial classes defined in this file with existing partials.
        
        Strategy:
        1. Identify partial symbols in current file
        2. Find existing partials with same FQN in same project/assembly
        3. designate the oldest one as 'primary'
        4. Update primary with list of all definition files and merged IDs
        """
        for symbol in created_symbols:
            if not symbol.is_partial:
                continue
            
            # Find other partials with same FQN and project/assembly
            # (excluding this symbol itself)
            stmt = select(Symbol).where(
                Symbol.fully_qualified_name == symbol.fully_qualified_name,
                Symbol.is_partial == 1,
                Symbol.id != symbol.id
            )
            
            if symbol.project_id:
                stmt = stmt.where(Symbol.project_id == symbol.project_id)
            elif symbol.assembly_name:
                stmt = stmt.where(Symbol.assembly_name == symbol.assembly_name)
            
            result = await self.session.execute(stmt)
            existing_partials = result.scalars().all()
            
            if existing_partials:
                # We found other parts.
                # Strategy: Pick the oldest one as "primary"
                all_partials = existing_partials + [symbol]
                # Sort by created_at (and id as tiebreaker)
                all_partials.sort(key=lambda s: (s.created_at, s.id))
                
                primary = all_partials[0]
                others = all_partials[1:]
                
                # Update primary
                definition_files = set()
                merged_ids = set()
                
                # Collect from primary
                if primary.partial_definition_files:
                    definition_files.update(primary.partial_definition_files)
                definition_files.add(primary.file_id)
                
                if primary.merged_from_partial_ids:
                    merged_ids.update(primary.merged_from_partial_ids)
                
                # Collect from others
                for other in others:
                    definition_files.add(other.file_id)
                    merged_ids.add(other.id)
                    # Also collect if they had their own lists (recursive merge)
                    if other.partial_definition_files:
                        definition_files.update(other.partial_definition_files)
                    if other.merged_from_partial_ids:
                        merged_ids.update(other.merged_from_partial_ids)
                
                primary.partial_definition_files = list(definition_files)
                primary.merged_from_partial_ids = list(merged_ids)
                
                await maybe_await(self.session.add(primary))



