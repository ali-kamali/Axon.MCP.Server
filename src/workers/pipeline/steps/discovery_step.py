import asyncio
import time
from typing import List, Optional
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import Repository
from src.config.enums import RepositoryStatusEnum, SourceControlProviderEnum
from src.gitlab.repository_manager import RepositoryManager
from src.azuredevops.repository_manager import AzureDevOpsRepositoryManager
from src.utils.file_exclusion import FileExclusionRules
from src.utils.redis_logger import RedisLogPublisher
from src.utils.logging_config import get_logger
from ..step import PipelineStep
from ..context import PipelineContext

logger = get_logger(__name__)

class DiscoveryStep(PipelineStep):
    """
    Step 2: Discover files in the repository and apply exclusion rules.
    Populates context.files with the list of files to process.
    """
    
    async def execute(self, ctx: PipelineContext) -> None:
        if not ctx.repo_path:
            raise ValueError("Repository path not set in context")
            
        publisher = RedisLogPublisher()
        start_time = time.time()
        repo = ctx.repository
        
        # Instantiate correct manager
        # Note: In a cleaner design, we might pass the manager in context or factory
        if repo.provider == SourceControlProviderEnum.GITLAB:
            repo_manager = RepositoryManager()
        elif repo.provider == SourceControlProviderEnum.AZUREDEVOPS:
            repo_manager = AzureDevOpsRepositoryManager()
        else:
            raise ValueError(f"Unsupported provider: {repo.provider}")

        # Get file tree
        files = await asyncio.to_thread(
            repo_manager.get_file_tree,
            ctx.repo_path
        )
        
        # Sort files path alphabetically to ensure files in the same project 
        # are processed consecutively. This is CRITICAL for Roslyn performance.
        files.sort()

        # Apply exclusion rules
        exclusion_rules = FileExclusionRules()
    
        # Parse .gitignore if it exists
        gitignore_path = ctx.repo_path / '.gitignore'
        if gitignore_path.exists():
            gitignore_patterns = FileExclusionRules.parse_gitignore(gitignore_path)
            exclusion_rules = FileExclusionRules(custom_exclusions=gitignore_patterns)
    
        # Filter files
        files_before = len(files)
        files = [f for f in files if not exclusion_rules.should_exclude(str(f.relative_to(ctx.repo_path)))]
        files_excluded = files_before - len(files)
    
        logger.info(
            "files_filtered",
            repository_id=ctx.repository_id,
            total_files=files_before,
            excluded=files_excluded,
            remaining=len(files)
        )
        
        # Store in context
        ctx.files = files
    
        # Update status to parsing
        repo.status = RepositoryStatusEnum.PARSING
        repo.total_files = len(files)
        await ctx.session.commit()
    
        logger.info(
            "repository_parsing_started",
            repository_id=ctx.repository_id,
            total_files=len(files)
        )
        await publisher.publish_log(ctx.repository_id, f"Starting to parse {len(files)} files...", details={"total_files": len(files)})
        
        ctx.metadata['exclusion_rules'] = exclusion_rules # Pass rules to next step if needed (though we filtering here)
        ctx.timings['discovery'] = time.time() - start_time
