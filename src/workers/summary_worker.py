"""
Celery tasks for module summarization.
"""

from celery import shared_task
import asyncio
import traceback

from src.workers.celery_app import celery_app
from src.workers.utils import _run_with_engine_cleanup
from src.database.session import AsyncSessionLocal
from src.utils.module_summary_generator import ModuleSummaryGenerator
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


async def _generate_module_summaries(session, repository_id: int, force_regenerate: bool = False) -> int:
    """
    Generate AI-powered summaries for modules in a repository.
    
    Args:
        session: Database session
        repository_id: Repository ID
        force_regenerate: Force regeneration of existing summaries
        
    Returns:
        Number of modules summarized
    """
    try:
        # Create generator (uses settings.llm_provider and settings.llm_model)
        generator = ModuleSummaryGenerator(session)
        
        # Generate summaries for all modules (depth 1-10)
        summaries = await generator.generate_summaries_for_repository(
            repository_id=repository_id,
            force_regenerate=force_regenerate,
            min_depth=1,
            max_depth=10
        )
        return len(summaries)
        
    except Exception as e:
        logger.error(
            "module_summary_generation_failed",
            repository_id=repository_id,
            error=str(e),
            traceback=traceback.format_exc()
        )
        return 0


@celery_app.task(
    bind=True,
    name="src.workers.tasks.generate_module_summaries_task",
    max_retries=2
)
def generate_module_summaries_task(self, repository_id: int, force_regenerate: bool = False):
    """
    Celery task to generate module summaries for a repository.
    
    Can be run independently or as part of the main sync pipeline.
    
    Args:
        repository_id: Repository ID
        force_regenerate: Regenerate existing summaries
        
    Returns:
        dict: Result summary with status and count
    """
    logger.info(
        "generate_module_summaries_task_started",
        repository_id=repository_id,
        task_id=self.request.id,
        force_regenerate=force_regenerate
    )
    
    try:
        result = asyncio.run(_run_with_engine_cleanup(
            _generate_module_summaries_task_async(self, repository_id, force_regenerate)
        ))
        return result
    except Exception as e:
        error_msg = f"Failed to generate module summaries: {str(e)}"
        logger.error(
            "generate_module_summaries_task_failed",
            repository_id=repository_id,
            error=error_msg,
            traceback=traceback.format_exc()
        )
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=30 * (2 ** self.request.retries))


async def _generate_module_summaries_task_async(task, repository_id: int, force_regenerate: bool):
    """Async implementation of module summary generation task."""
    
    async with AsyncSessionLocal() as session:
        try:
            # Uses settings.llm_provider and settings.llm_model
            generator = ModuleSummaryGenerator(session)
            
            summaries = await generator.generate_summaries_for_repository(
                repository_id=repository_id,
                force_regenerate=force_regenerate,
                min_depth=1,
                max_depth=10
            )
            
            await session.commit()
            
            logger.info(
                "module_summaries_generated",
                repository_id=repository_id,
                count=len(summaries)
            )
            
            return {
                "status": "success",
                "repository_id": repository_id,
                "modules_summarized": len(summaries)
            }
            
        except Exception as e:
            await session.rollback()
            logger.error(
                "module_summary_generation_failed",
                repository_id=repository_id,
                error=str(e),
                traceback=traceback.format_exc()
            )
            return {
                "status": "error",
                "repository_id": repository_id,
                "error": str(e)
            }
