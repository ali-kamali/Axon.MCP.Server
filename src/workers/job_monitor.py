"""
Job monitoring and management for background workers.

This module provides functionality to monitor running jobs,
detect stuck jobs, and retry failed jobs.
"""

from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from src.database.models import Job, Repository
from src.config.enums import JobStatusEnum, RepositoryStatusEnum
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class JobMonitor:
    """Monitor and manage background jobs."""
    
    def __init__(self, session: AsyncSession):
        """
        Initialize job monitor.
        
        Args:
            session: Database session
        """
        self.session = session
        # Fix: Prevent attribute expiration on commit to avoid MissingGreenlet errors
        # when accessing job attributes after status updates
        self.session.expire_on_commit = False
    
    async def get_running_jobs(self) -> List[Job]:
        """
        Get all currently running jobs.
        
        Returns:
            List of running Job objects
        """
        result = await self.session.execute(
            select(Job).where(Job.status == JobStatusEnum.RUNNING)
        )
        jobs = result.scalars().all()
        logger.info("fetched_running_jobs", count=len(jobs))
        return jobs
    
    async def get_pending_jobs(self) -> List[Job]:
        """
        Get all pending jobs waiting to be processed.
        
        Returns:
            List of pending Job objects
        """
        result = await self.session.execute(
            select(Job)
            .where(Job.status == JobStatusEnum.PENDING)
            .order_by(Job.created_at)
        )
        jobs = result.scalars().all()
        logger.info("fetched_pending_jobs", count=len(jobs))
        return jobs
    
    async def get_failed_jobs(self, limit: int = 100) -> List[Job]:
        """
        Get recent failed jobs.
        
        Args:
            limit: Maximum number of jobs to return
            
        Returns:
            List of failed Job objects
        """
        result = await self.session.execute(
            select(Job)
            .where(Job.status == JobStatusEnum.FAILED)
            .order_by(Job.updated_at.desc())
            .limit(limit)
        )
        jobs = result.scalars().all()
        logger.info("fetched_failed_jobs", count=len(jobs))
        return jobs
    
    async def get_stuck_jobs(self, timeout_minutes: int = 60) -> List[Job]:
        """
        Get jobs that have been running too long.
        
        Args:
            timeout_minutes: Consider job stuck after this duration
            
        Returns:
            List of stuck Job objects
        """
        cutoff = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        
        result = await self.session.execute(
            select(Job).where(
                Job.status == JobStatusEnum.RUNNING,
                Job.started_at < cutoff
            )
        )
        stuck_jobs = result.scalars().all()
        
        if stuck_jobs:
            logger.warning(
                "stuck_jobs_detected",
                count=len(stuck_jobs),
                timeout_minutes=timeout_minutes
            )
        
        return stuck_jobs
    
    async def mark_job_as_stuck(self, job_id: int) -> bool:
        """
        Mark a job as failed due to being stuck.
        
        Args:
            job_id: Job ID to mark as stuck
            
        Returns:
            bool: True if marked successfully
        """
        result = await self.session.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        
        if not job:
            logger.error("job_not_found", job_id=job_id)
            return False
        
        job.status = JobStatusEnum.FAILED
        job.completed_at = datetime.utcnow()
        job.error_message = "Job exceeded maximum execution time and was marked as stuck"
        
        if job.started_at:
            duration = (job.completed_at - job.started_at).total_seconds()
            job.duration_seconds = int(duration)
        
        # Also update repository status if applicable
        if job.repository_id:
            repo_result = await self.session.execute(
                select(Repository).where(Repository.id == job.repository_id)
            )
            repo = repo_result.scalar_one_or_none()
            if repo and repo.status not in [
                RepositoryStatusEnum.COMPLETED,
                RepositoryStatusEnum.FAILED
            ]:
                repo.status = RepositoryStatusEnum.FAILED
        
        await self.session.commit()
        
        logger.info("job_marked_as_stuck", job_id=job_id)
        return True
    
    async def retry_failed_job(self, job_id: int) -> bool:
        """
        Retry a failed job.
        
        Args:
            job_id: Job ID to retry
            
        Returns:
            bool: True if retry initiated
        """
        result = await self.session.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        
        if not job:
            logger.error("job_not_found", job_id=job_id)
            return False
        
        if job.status != JobStatusEnum.FAILED:
            logger.warning(
                "job_not_failed",
                job_id=job_id,
                status=job.status.value
            )
            return False
        
        if job.retry_count >= job.max_retries:
            logger.warning(
                "max_retries_exceeded",
                job_id=job_id,
                retry_count=job.retry_count,
                max_retries=job.max_retries
            )
            return False
        
        # Update job for retry
        # CRITICAL: Save original retry_count to rollback if queueing fails
        original_retry_count = job.retry_count
        
        job.status = JobStatusEnum.PENDING
        job.retry_count += 1
        job.error_message = None
        job.error_traceback = None
        job.started_at = None
        job.completed_at = None
        job.duration_seconds = None
        
        # Update repository status if applicable
        # CRITICAL: Save original repository status for rollback if queueing fails
        repo = None
        old_repo_status = None
        if job.repository_id:
            repo_result = await self.session.execute(
                select(Repository).where(Repository.id == job.repository_id)
            )
            repo = repo_result.scalar_one_or_none()
            if repo:
                old_repo_status = repo.status  # Save for rollback
                repo.status = RepositoryStatusEnum.PENDING
        
        # CRITICAL: Generate task ID BEFORE queuing to avoid race condition
        # We must:
        # 1. Generate new task ID
        # 2. Update job.celery_task_id in DB
        # 3. Commit the change
        # 4. THEN queue the task with that ID
        # 5. If queueing fails, rollback job AND repository to original state
        # This prevents worker from starting before DB update is visible
        
        import uuid
        new_task_id = str(uuid.uuid4())
        old_task_id = job.celery_task_id  # Save old ID in case we need to rollback
        job.celery_task_id = new_task_id
        
        # Commit the updated task ID BEFORE queueing
        await self.session.commit()
        
        # Now queue the task with the pre-assigned ID
        # Wrap in try/except to handle queueing failures
        task_queued = False
        try:
            if job.job_type == "sync_repository":
                from src.workers.tasks import sync_repository
                sync_repository.apply_async(
                    args=[job.repository_id],
                    task_id=new_task_id
                )
                task_queued = True
            elif job.job_type == "parse_file":
                from src.workers.tasks import parse_file_task
                # Would need file_id from metadata
                file_id = job.job_metadata.get("file_id") if job.job_metadata else None
                if file_id:
                    parse_file_task.apply_async(
                        args=[file_id],
                        task_id=new_task_id
                    )
                    task_queued = True
                else:
                    logger.error(
                        "job_retry_missing_metadata",
                        job_id=job_id,
                        job_type=job.job_type,
                        reason="file_id not found in job_metadata"
                    )
            elif job.job_type == "generate_embeddings":
                from src.workers.tasks import generate_embeddings_task
                # Would need chunk_ids from metadata
                chunk_ids = job.job_metadata.get("chunk_ids") if job.job_metadata else None
                if chunk_ids:
                    generate_embeddings_task.apply_async(
                        args=[chunk_ids],
                        task_id=new_task_id
                    )
                    task_queued = True
                else:
                    logger.error(
                        "job_retry_missing_metadata",
                        job_id=job_id,
                        job_type=job.job_type,
                        reason="chunk_ids not found in job_metadata"
                    )
            
            if task_queued:
                logger.info(
                    "job_retry_initiated",
                    job_id=job_id,
                    retry_count=job.retry_count,
                    job_type=job.job_type,
                    new_task_id=new_task_id
                )
                return True
            else:
                # Could not queue - rollback job AND repository to FAILED state
                logger.warning(
                    "job_retry_not_queued_missing_metadata",
                    job_id=job_id,
                    job_type=job.job_type
                )
                job.status = JobStatusEnum.FAILED
                job.celery_task_id = old_task_id
                job.retry_count = original_retry_count  # Rollback retry count
                job.error_message = "Retry failed: missing metadata to queue task"
                
                # CRITICAL: Restore repository status
                if repo and old_repo_status:
                    repo.status = old_repo_status
                    logger.info(
                        "repository_status_restored_after_retry_failure",
                        repository_id=job.repository_id,
                        restored_status=old_repo_status.value
                    )
                
                await self.session.commit()
                return False
                
        except Exception as e:
            # Queueing failed - rollback job AND repository to original state
            logger.error(
                "job_retry_queueing_failed",
                job_id=job_id,
                job_type=job.job_type,
                error=str(e)
            )
            
            # Restore job to original state
            job.status = JobStatusEnum.FAILED
            job.celery_task_id = old_task_id
            job.retry_count = original_retry_count  # Rollback retry count
            job.error_message = f"Retry failed: could not queue task - {str(e)}"
            
            # CRITICAL: Restore repository status
            if repo and old_repo_status:
                repo.status = old_repo_status
                logger.info(
                    "repository_status_restored_after_retry_failure",
                    repository_id=job.repository_id,
                    restored_status=old_repo_status.value,
                    error=str(e)
                )
            
            await self.session.commit()
            
            return False
    
    async def cancel_job(self, job_id: int, reason: str = "Cancelled by user") -> bool:
        """
        Cancel a pending or running job.
        
        Args:
            job_id: Job ID to cancel
            reason: Cancellation reason
            
        Returns:
            bool: True if cancelled successfully
        """
        result = await self.session.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        
        if not job:
            logger.error("job_not_found", job_id=job_id)
            return False
        
        if job.status in [JobStatusEnum.COMPLETED, JobStatusEnum.CANCELLED]:
            logger.warning(
                "job_cannot_be_cancelled",
                job_id=job_id,
                status=job.status.value
            )
            return False
        
        # Update job status
        job.status = JobStatusEnum.CANCELLED
        job.completed_at = datetime.utcnow()
        job.error_message = reason
        
        if job.started_at:
            duration = (job.completed_at - job.started_at).total_seconds()
            job.duration_seconds = int(duration)
        
        await self.session.commit()
        
        # Attempt to revoke Celery task if it hasn't started
        if job.celery_task_id:
            try:
                from src.workers.celery_app import celery_app
                celery_app.control.revoke(job.celery_task_id, terminate=True)
                logger.info("celery_task_revoked", task_id=job.celery_task_id)
            except Exception as e:
                logger.error(
                    "celery_task_revoke_failed",
                    task_id=job.celery_task_id,
                    error=str(e)
                )
        
        logger.info("job_cancelled", job_id=job_id, reason=reason)
        return True
    
    async def get_job_stats(self) -> Dict[str, int]:
        """
        Get statistics about jobs.
        
        Returns:
            Dictionary with job statistics
        """
        stats = {
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
            "total": 0
        }
        
        for status in JobStatusEnum:
            result = await self.session.execute(
                select(Job).where(Job.status == status)
            )
            count = len(result.scalars().all())
            stats[status.value] = count
            stats["total"] += count
        
        logger.info("job_stats_calculated", stats=stats)
        return stats
    
    async def cleanup_old_jobs(self, days: int = 30) -> int:
        """
        Clean up completed/failed jobs older than specified days.
        
        Args:
            days: Delete jobs older than this many days
            
        Returns:
            Number of jobs deleted
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        result = await self.session.execute(
            select(Job).where(
                Job.status.in_([
                    JobStatusEnum.COMPLETED,
                    JobStatusEnum.FAILED,
                    JobStatusEnum.CANCELLED
                ]),
                Job.updated_at < cutoff
            )
        )
        old_jobs = result.scalars().all()
        
        for job in old_jobs:
            await self.session.delete(job)
        
        await self.session.commit()
        
        logger.info(
            "old_jobs_cleaned_up",
            count=len(old_jobs),
            days=days
        )
        
        return len(old_jobs)

    async def reset_running_jobs_on_startup(self) -> int:
        """
        Reset jobs that were left running when the server shut down.
        
        This should be called on application startup to ensure no jobs
        are stuck in the RUNNING state from a previous session.
        
        Returns:
            Number of jobs reset
        """
        # Find all running jobs
        result = await self.session.execute(
            select(Job).where(Job.status == JobStatusEnum.RUNNING)
        )
        running_jobs = result.scalars().all()
        
        if not running_jobs:
            return 0
            
        reset_count = 0
        for job in running_jobs:
            logger.warning(
                "resetting_interrupted_job",
                job_id=job.id,
                job_type=job.job_type,
                started_at=str(job.started_at)
            )
            
            # Mark job as failed
            job.status = JobStatusEnum.FAILED
            job.completed_at = datetime.utcnow()
            job.error_message = "Job interrupted by system restart"
            
            if job.started_at:
                duration = (job.completed_at - job.started_at).total_seconds()
                job.duration_seconds = int(duration)
                
            # Also update repository status if it's in an active state
            if job.repository_id:
                repo_result = await self.session.execute(
                    select(Repository).where(Repository.id == job.repository_id)
                )
                repo = repo_result.scalar_one_or_none()
                
                if repo and repo.status in [
                    RepositoryStatusEnum.CLONING,
                    RepositoryStatusEnum.PARSING,
                    RepositoryStatusEnum.EXTRACTING,
                    RepositoryStatusEnum.EMBEDDING
                ]:
                    logger.warning(
                        "resetting_interrupted_repository",
                        repository_id=repo.id,
                        old_status=repo.status.value
                    )
                    repo.status = RepositoryStatusEnum.FAILED
            
            reset_count += 1
            
        await self.session.commit()
        logger.info("startup_job_cleanup_completed", reset_count=reset_count)
        return reset_count

