"""
Celery tasks for linking microservices.
"""

from celery import shared_task
from typing import Optional, List
from datetime import datetime
import asyncio
import traceback

from src.workers.celery_app import celery_app
from src.workers.utils import _run_with_engine_cleanup
from src.database.session import AsyncSessionLocal
from src.database.models import Job
from src.config.enums import JobStatusEnum
from src.services.link_service import LinkService
from src.utils.redis_logger import RedisLogPublisher
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="src.workers.tasks.link_microservices",
    max_retries=3,
    time_limit=3600  # 1 hour timeout
)
def link_microservices(self, repository_ids: Optional[List[int]] = None):
    """
    Link microservices: Connect API calls to endpoints and events to subscribers.
    
    This is the main task for Phase 3: The Linker. It:
    1. Parses gateway configurations (Ocelot, Nginx) to understand routing
    2. Links frontend API calls to backend endpoints using fuzzy matching
    3. Links event publishers to subscribers across repositories
    
    The task can be run:
    - Globally (repository_ids=None): Links across all repositories
    - Selectively: Links only specified repositories
    
    Args:
        repository_ids: Optional list of repository IDs to process
        
    Returns:
        dict: Result summary with link counts
    """
    logger.info(
        "link_microservices_task_started",
        repository_ids=repository_ids,
        task_id=self.request.id
    )
    
    try:
        result = asyncio.run(_run_with_engine_cleanup(
            _link_microservices_async(self, repository_ids)
        ))
        return result
    except Exception as e:
        error_msg = f"Failed to link microservices: {str(e)}"
        logger.error(
            "link_microservices_task_failed",
            repository_ids=repository_ids,
            error=error_msg,
            traceback=traceback.format_exc()
        )
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


async def _link_microservices_async(task, repository_ids: Optional[List[int]] = None):
    """Async implementation of microservices linking."""
    
    publisher = RedisLogPublisher()
    await publisher.connect()
    
    try:
        async with AsyncSessionLocal() as session:
            session.expire_on_commit = False # Fix: Prevent attribute expiration on commit
            try:
                # Create job record
                job = Job(
                    job_type="link_microservices",
                    status=JobStatusEnum.RUNNING,
                    celery_task_id=task.request.id,
                    started_at=datetime.utcnow(),
                    job_metadata={"repository_ids": repository_ids}
                )
                session.add(job)
                await session.commit()
                await session.refresh(job)
                
                logger.info(
                    "link_microservices_job_created",
                    job_id=job.id,
                    repository_ids=repository_ids
                )
                
                # Create LinkService and run linking
                link_service = LinkService(session)
                
                # Update task state
                task.update_state(
                    state='PROGRESS',
                    meta={
                        'status': 'parsing_gateways',
                        'phase': 'gateway_parsing'
                    }
                )
                
                # Run the complete linking process
                results = await link_service.link_all(repository_ids)
                
                await session.commit()
                
                # Update job with results
                job.status = JobStatusEnum.COMPLETED
                job.completed_at = datetime.utcnow()
                job.duration_seconds = int(
                    (job.completed_at - job.started_at).total_seconds()
                )
                job.job_metadata = {
                    "repository_ids": repository_ids,
                    **results
                }
                
                await session.commit()
                
                logger.info(
                    "link_microservices_completed",
                    job_id=job.id,
                    **results
                )
                
                return {
                    "status": "success",
                    "job_id": job.id,
                    **results,
                    "duration_seconds": job.duration_seconds
                }
                
            except Exception as e:
                error_msg = f"Failed to link microservices: {str(e)}"
                logger.error(
                    "link_microservices_failed",
                    error=error_msg,
                    traceback=traceback.format_exc()
                )
                await session.rollback()
                raise
                
    finally:
        await publisher.close()


@celery_app.task(
    bind=True,
    name="src.workers.tasks.link_repository",
    max_retries=3
)
def link_repository(self, repository_id: int):
    """
    Link a single repository's API calls and events.
    
    This is a convenience task for linking a single repository after it's been synced.
    It's typically called as a follow-up to sync_repository.
    
    Args:
        repository_id: Repository ID to link
        
    Returns:
        dict: Result summary with link counts
    """
    logger.info(
        "link_repository_task_started",
        repository_id=repository_id,
        task_id=self.request.id
    )
    
    try:
        result = asyncio.run(_run_with_engine_cleanup(
            _link_microservices_async(self, [repository_id])
        ))
        return result
    except Exception as e:
        error_msg = f"Failed to link repository: {str(e)}"
        logger.error(
            "link_repository_task_failed",
            repository_id=repository_id,
            error=error_msg,
            traceback=traceback.format_exc()
        )
        raise self.retry(exc=e, countdown=30 * (2 ** self.request.retries))
