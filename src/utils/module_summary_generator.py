"""Module summary generation and management for Phase 2."""

import hashlib
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import File, ModuleSummary, Repository
from src.utils.llm_summarizer import LLMSummarizer
from src.utils.logging_config import get_logger
from src.utils.module_identifier import ModuleIdentifier, ModuleInfo

logger = get_logger(__name__)


class ModuleSummaryGenerator:
    """Generate and manage module summaries."""

    def __init__(self, session: AsyncSession, llm_provider: str = None, llm_model: str = None):
        """
        Initialize module summary generator.

        Args:
            session: Database session
            llm_provider: LLM provider for summarization (uses settings if None)
            llm_model: LLM model to use (uses settings if None)
        """
        self.session = session
        self.module_identifier = ModuleIdentifier(session)
        self.llm_summarizer = LLMSummarizer(provider=llm_provider, model=llm_model)

    async def generate_summaries_for_repository(
        self,
        repository_id: int,
        force_regenerate: bool = False,
        min_depth: int = 1,
        max_depth: int = 3,
    ) -> List[ModuleSummary]:
        """
        Generate summaries for all modules in a repository.

        Args:
            repository_id: Repository ID
            force_regenerate: Regenerate even if summaries exist
            min_depth: Minimum directory depth for modules
            max_depth: Maximum directory depth for modules

        Returns:
            List of generated/updated ModuleSummary objects
        """
        try:
            # Identify modules
            modules = await self.module_identifier.identify_modules(
                repository_id, min_depth, max_depth
            )

            if not modules:
                logger.info(f"No modules found for repository {repository_id}")
                return []

            logger.info(
                f"Found {len(modules)} modules in repository {repository_id}"
            )

            summaries = []
            for module in modules:
                try:
                    summary = await self.generate_or_update_summary(
                        repository_id, module, force_regenerate
                    )
                    if summary:
                        summaries.append(summary)
                except Exception as e:
                    logger.error(
                        f"Error generating summary for module {module.path}: {e}",
                        exc_info=True,
                    )
                    continue

            logger.info(
                f"Generated {len(summaries)} summaries for repository {repository_id}"
            )
            return summaries

        except Exception as e:
            logger.error(
                f"Error generating summaries for repository: {e}", exc_info=True
            )
            return []

    async def generate_or_update_summary(
        self,
        repository_id: int,
        module_info: ModuleInfo,
        force_regenerate: bool = False,
    ) -> Optional[ModuleSummary]:
        """
        Generate or update summary for a single module.

        Args:
            repository_id: Repository ID
            module_info: Module information
            force_regenerate: Force regeneration even if exists

        Returns:
            ModuleSummary object or None
        """
        try:
            # Check if summary already exists
            existing = await self.session.execute(
                select(ModuleSummary)
                .where(
                    ModuleSummary.repository_id == repository_id,
                    ModuleSummary.module_path == module_info.path,
                )
                .order_by(ModuleSummary.last_updated.desc())
            )
            summaries = existing.scalars().all()

            if len(summaries) > 1:
                # Handle duplicates: keep the most recent one (first in list due to order_by)
                existing_summary = summaries[0]
                logger.warning(
                    f"Found {len(summaries)} summaries for {module_info.path}, "
                    f"keeping latest (ID: {existing_summary.id}) and removing duplicates"
                )
                
                # Delete older duplicates
                for duplicate in summaries[1:]:
                    await self.session.delete(duplicate)
                
                # Flush to ensure deletions happen before any updates
                await self.session.flush()
            elif summaries:
                existing_summary = summaries[0]
            else:
                existing_summary = None

            # Calculate current module hash
            current_hash = await self._calculate_module_hash(
                repository_id, module_info.path
            )

            # Skip regeneration if content hasn't changed
            if existing_summary and not force_regenerate:
                if existing_summary.content_hash == current_hash:
                    logger.debug(
                        f"Summary for module {module_info.path} is up-to-date "
                        f"(hash: {current_hash}), skipping regeneration"
                    )
                    return existing_summary
                else:
                    logger.info(
                        f"Module {module_info.path} content changed "
                        f"(old: {existing_summary.content_hash}, new: {current_hash}), "
                        f"regenerating summary"
                    )

            # Get key symbols for this module
            symbol_list = await self.module_identifier.get_module_symbols(
                repository_id, module_info.path, limit=20
            )

            # Get sample file contents for entry points (if any)
            file_contents = await self._get_entry_point_contents(
                repository_id, module_info
            )

            # Generate summary using LLM
            summary_data = await self.llm_summarizer.summarize_module(
                module_info, symbol_list, file_contents
            )

            if not summary_data:
                logger.warning(f"Failed to generate summary for {module_info.path}")
                return None

            # Prepare entry points list
            entry_points_data = [
                {
                    "file": ep,
                    "type": self._classify_entry_point(ep),
                }
                for ep in module_info.entry_points
            ]

            # Create or update database record
            if existing_summary:
                # Update existing
                existing_summary.summary = summary_data.get("summary", "")
                existing_summary.purpose = summary_data.get("purpose")
                existing_summary.key_components = summary_data.get("key_components", [])
                existing_summary.dependencies = summary_data.get("dependencies", {})
                existing_summary.entry_points = entry_points_data
                existing_summary.file_count = module_info.file_count
                existing_summary.symbol_count = module_info.symbol_count
                existing_summary.line_count = module_info.line_count
                existing_summary.complexity_score = summary_data.get("complexity_score")
                existing_summary.generated_by = f"{self.llm_summarizer.provider}:{self.llm_summarizer.model}"
                existing_summary.content_hash = current_hash
                existing_summary.last_updated = datetime.utcnow()
                existing_summary.version += 1

                module_summary = existing_summary
                logger.info(f"Updated summary for module {module_info.path}")

            else:
                # Create new
                module_summary = ModuleSummary(
                    repository_id=repository_id,
                    module_path=module_info.path,
                    module_name=module_info.name,
                    module_type=module_info.module_type,
                    is_package=1 if module_info.is_package else 0,
                    summary=summary_data.get("summary", ""),
                    purpose=summary_data.get("purpose"),
                    key_components=summary_data.get("key_components", []),
                    dependencies=summary_data.get("dependencies", {}),
                    entry_points=entry_points_data,
                    file_count=module_info.file_count,
                    symbol_count=module_info.symbol_count,
                    line_count=module_info.line_count,
                    complexity_score=summary_data.get("complexity_score"),
                    generated_by=f"{self.llm_summarizer.provider}:{self.llm_summarizer.model}",
                    content_hash=current_hash,
                    generated_at=datetime.utcnow(),
                    last_updated=datetime.utcnow(),
                    version=1,
                )

                self.session.add(module_summary)
                logger.info(f"Created new summary for module {module_info.path}")

            # Commit to database
            await self.session.commit()

            return module_summary

        except Exception as e:
            logger.error(
                f"Error generating/updating summary for {module_info.path}: {e}",
                exc_info=True,
            )
            await self.session.rollback()
            return None

    async def get_module_summary(
        self, repository_id: int, module_path: str, generate_if_missing: bool = True
    ) -> Optional[ModuleSummary]:
        """
        Get module summary, optionally generating it if missing.

        Args:
            repository_id: Repository ID
            module_path: Path to module
            generate_if_missing: Generate summary if it doesn't exist

        Returns:
            ModuleSummary object or None
        """
        try:
            # Try to get existing summary
            result = await self.session.execute(
                select(ModuleSummary)
                .where(
                    ModuleSummary.repository_id == repository_id,
                    ModuleSummary.module_path == module_path,
                )
                .order_by(ModuleSummary.last_updated.desc())
            )
            # Use first() to get the most recent one (or None) and ignore duplicates
            summary = result.scalars().first()

            if summary or not generate_if_missing:
                return summary

            # Generate if missing
            logger.info(
                f"Summary not found for {module_path}, generating on-demand..."
            )

            # Identify this specific module
            modules = await self.module_identifier.identify_modules(
                repository_id, min_depth=0, max_depth=10
            )

            module_info = next(
                (m for m in modules if m.path == module_path), None
            )

            if not module_info:
                logger.warning(f"Module not found: {module_path}")
                return None

            # Generate summary
            summary = await self.generate_or_update_summary(
                repository_id, module_info, force_regenerate=False
            )

            return summary

        except Exception as e:
            logger.error(f"Error getting module summary: {e}", exc_info=True)
            return None

    async def list_module_summaries(
        self, repository_id: int, module_type: Optional[str] = None
    ) -> List[ModuleSummary]:
        """
        List all module summaries for a repository.

        Args:
            repository_id: Repository ID
            module_type: Optional filter by module type

        Returns:
            List of ModuleSummary objects
        """
        try:
            query = select(ModuleSummary).where(
                ModuleSummary.repository_id == repository_id
            )

            if module_type:
                query = query.where(ModuleSummary.module_type == module_type)

            query = query.order_by(ModuleSummary.module_path)

            result = await self.session.execute(query)
            summaries = result.scalars().all()

            return list(summaries)

        except Exception as e:
            logger.error(f"Error listing module summaries: {e}", exc_info=True)
            return []

    async def _get_entry_point_contents(
        self, repository_id: int, module_info: ModuleInfo
    ) -> Dict[str, str]:
        """
        Get contents of entry point files for a module.
        
        Note: Currently returns empty dict because File model doesn't store content.
        To implement this would require:
        1. Reading files from disk/repository clone
        2. Caching file contents or extending File model
        3. Managing file size limits for summaries
        
        For now, entry point file names are included in module summary metadata,
        which provides navigation hints without the token overhead of full contents.
        """
        if not module_info.entry_points:
            return {}

        try:
            # Get entry point files (for future implementation)
            entry_point_paths = [
                f"{module_info.path}/{ep}" for ep in module_info.entry_points
            ]

            result = await self.session.execute(
                select(File).where(
                    File.repository_id == repository_id,
                    File.path.in_(entry_point_paths),
                )
            )
            files = result.scalars().all()

            # File model doesn't store content - would need disk read implementation
            return {}

        except Exception as e:
            logger.error(f"Error getting entry point contents: {e}", exc_info=True)
            return {}

    async def _calculate_module_hash(self, repository_id: int, module_path: str) -> str:
        """
        Calculate a hash of the module's content based on file content hashes.
        
        This hash is used to detect if the module content has changed since the
        last summary generation.
        
        Args:
            repository_id: Repository ID
            module_path: Path to module
            
        Returns:
            SHA256 hash of the combined file content hashes
        """
        try:
            # Get all files in this module (including subdirectories)
            files_result = await self.session.execute(
                select(File)
                .where(
                    File.repository_id == repository_id,
                    File.path.like(f"{module_path}%"),
                )
                .order_by(File.path)
            )
            files = files_result.scalars().all()
            
            if not files:
                logger.warning(f"No files found for module {module_path}")
                return ""
            
            # Combine all file content hashes in a deterministic order
            hasher = hashlib.sha256()
            for file in files:
                # Use file path and content hash to create a stable hash
                file_hash = file.content_hash or ""
                hasher.update(f"{file.path}:{file_hash}".encode('utf-8'))
            
            module_hash = hasher.hexdigest()
            logger.debug(f"Calculated module hash for {module_path}: {module_hash}")
            return module_hash
            
        except Exception as e:
            logger.error(f"Error calculating module hash: {e}", exc_info=True)
            return ""

    def _classify_entry_point(self, filename: str) -> str:
        """Classify entry point type based on filename."""
        if filename == "__init__.py":
            return "package_init"
        elif filename in ["main.py", "main.ts", "main.js"]:
            return "application_main"
        elif filename in ["index.ts", "index.tsx", "index.js", "index.jsx"]:
            return "module_index"
        elif filename in ["app.py", "App.tsx", "App.jsx"]:
            return "application_entry"
        elif filename == "__main__.py":
            return "python_main"
        else:
            return "entry_point"

