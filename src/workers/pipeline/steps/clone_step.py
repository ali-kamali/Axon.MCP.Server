import asyncio
import time
from typing import Optional
from sqlalchemy import select

from src.config.enums import SourceControlProviderEnum, RepositoryStatusEnum
from src.database.models import Repository, Commit
from src.gitlab.repository_manager import RepositoryManager
from src.azuredevops.repository_manager import AzureDevOpsRepositoryManager
from src.utils.redis_logger import RedisLogPublisher
from src.utils.logging_config import get_logger
from ..step import PipelineStep
from ..context import PipelineContext

logger = get_logger(__name__)

class CloneStep(PipelineStep):
    """
    Step 1: Clone or update the repository.
    """
    
    async def execute(self, ctx: PipelineContext) -> None:
        publisher = RedisLogPublisher()
        start_time = time.time()
        
        # Ensure repository object is loaded
        if not ctx.repository:
            result = await ctx.session.execute(
                select(Repository).where(Repository.id == ctx.repository_id)
            )
            ctx.repository = result.scalar_one_or_none()
            
        if not ctx.repository:
            raise ValueError(f"Repository {ctx.repository_id} not found")
            
        repo = ctx.repository
        
        # Update status
        repo.status = RepositoryStatusEnum.CLONING
        await ctx.session.commit()
        
        logger.info("repository_cloning_started", repository_id=ctx.repository_id, provider=repo.provider)
        await publisher.publish_log(ctx.repository_id, f"Cloning repository from {repo.provider}...", details={"provider": repo.provider})
        
        try:
            repo_path = None
            
            # Select appropriate repository manager
            if repo.provider == SourceControlProviderEnum.GITLAB:
                repo_manager = RepositoryManager()
                repo_path = await asyncio.to_thread(
                    repo_manager.clone_or_update,
                    repo.url,
                    repo.path_with_namespace,
                    repo.default_branch
                )
            elif repo.provider == SourceControlProviderEnum.AZUREDEVOPS:
                repo_manager = AzureDevOpsRepositoryManager()
                repo_path = await asyncio.to_thread(
                    repo_manager.clone_or_update_repository,
                    repo.azuredevops_project_name,
                    repo.name,
                    repo.clone_url,
                    repo.default_branch
                )
            else:
                raise ValueError(f"Unsupported provider: {repo.provider}")
                
            # Store in context
            ctx.repo_path = repo_path
            
            logger.info(
                "repository_cloned",
                repository_id=ctx.repository_id,
                path=str(repo_path)
            )
            await publisher.publish_log(ctx.repository_id, "Repository cloned successfully.", details={"path": str(repo_path)})
            
            # Extract last commit info
            try:
                commit_info = repo_manager.get_head_commit(repo_path)
                if commit_info:
                    # Update Repository
                    repo.last_commit_sha = commit_info["sha"]
                    
                    # Create or Update Commit record
                    # Check if commit exists
                    stmt = select(Commit).where(Commit.sha == commit_info["sha"])
                    result = await ctx.session.execute(stmt)
                    existing_commit = result.scalar_one_or_none()
                    
                    if not existing_commit:
                        new_commit = Commit(
                            repository_id=repo.id,
                            sha=commit_info["sha"],
                            message=commit_info["message"],
                            author_name=commit_info["author_name"],
                            author_email=commit_info["author_email"],
                            committed_date=commit_info["committed_date"],
                            parent_sha=commit_info["parent_sha"]
                        )
                        ctx.session.add(new_commit)
                        logger.info("commit_record_created", sha=commit_info["sha"], repository_id=repo.id)
                    else:
                        # Ensure it's linked to this repo (though SHA should be unique globally in git, 
                        # our model has repository_id, so technically we could have same SHA in different repos if forks?
                        # Actually Commit model has unique=True on SHA, so it's one global commit table?
                        # Let's check model... 
                        # sha = Column(String(40), nullable=False, unique=True, index=True)
                        # Yes, unique. So if it exists, we just ensure repository_id matches? 
                        # Wait, if multiple repos have same commit (forks), unique constraint on SHA might be problematic 
                        # if we want to associate it with *this* repository.
                        # BUT, looking at models.py: 
                        # repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
                        # So a Commit belongs to ONE repository. 
                        # If two repos have same commit, we can't store it twice with same SHA.
                        # This schema seems to assume commits are unique PER REPOSITORY or valid only for one.
                        # Ref: models.py line 169: sha = Column(String(40), nullable=False, unique=True, index=True)
                        # Only one record per SHA.
                        pass

                    # However, if we look at the model, Commit has repository_id.
                    # This implies if Repo A and Repo B share a commit, we can only store it for one of them?
                    # That seems like a schema limitation if forks are involved.
                    # For now, I will proceed with logic: if exists, don't create. 
                    # If it belongs to another repo, that's a data modeling issue out of scope check,
                    # but typically standard sync won't hit this unless we strictly enforce uniqueness globally.
                    
                    await ctx.session.flush()
                    
                    logger.info(
                        "last_commit_updated", 
                        repository_id=repo.id, 
                        commit_sha=repo.last_commit_sha
                    )
            except Exception as e:
                logger.error("failed_to_extract_commit_info", error=str(e))
                # Don't fail the sync just because commit info failed? 
                # Or maybe we should log it but continue.
                await publisher.publish_log(ctx.repository_id, f"Warning: Failed to extract last commit info: {str(e)}", level="WARNING")

            
        except Exception as e:
            await publisher.publish_log(ctx.repository_id, f"Cloning failed: {str(e)}", level="ERROR")
            raise

        ctx.timings['clone'] = time.time() - start_time

    async def can_skip(self, ctx: PipelineContext) -> bool:
        # We could skip if repo_path is already set and valid, but usually we want to ensure up-to-date.
        # For now, never skip unless testing.
        return False
