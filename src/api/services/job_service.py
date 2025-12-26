"""Job service utilities."""

from __future__ import annotations

from typing import List, Optional
from uuid import uuid4

from sqlalchemy import Select, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.jobs import JobDetailResponse, JobResponse
from src.config.enums import JobStatusEnum, RepositoryStatusEnum
from src.database.models import Job, Repository
from src.utils.logging_config import get_logger


logger = get_logger(__name__)


class JobService:
    """Encapsulates job CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self,
        *,
        offset: int,
        limit: int,
        status: Optional[JobStatusEnum] = None,
        repository_id: Optional[int] = None,
    ) -> tuple[List[JobResponse], int]:
        """List jobs with optional status/repository filter and pagination."""
        stmt: Select = select(Job).offset(offset).limit(limit).order_by(Job.created_at.desc())
        
        if status:
            stmt = stmt.where(Job.status == status)
        
        if repository_id:
            stmt = stmt.where(Job.repository_id == repository_id)
        
        result = await self._session.execute(stmt)
        jobs = result.scalars().all()
        
        # Get total count
        count_stmt = select(func.count(Job.id))
        if status:
            count_stmt = count_stmt.where(Job.status == status)
        if repository_id:
            count_stmt = count_stmt.where(Job.repository_id == repository_id)
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar() or 0
        
        return [JobResponse.model_validate(job) for job in jobs], total

    async def get(self, job_id: int) -> Optional[JobDetailResponse]:
        """Get a single job by ID with full details."""
        job = await self._session.get(Job, job_id)
        if job is None:
            return None
        return JobDetailResponse.model_validate(job)

    async def retry(self, job_id: int) -> Optional[JobDetailResponse]:
        """Retry a failed job and enqueue the corresponding Celery task."""
        job = await self._session.get(Job, job_id)
        if job is None:
            return None

        if job.status != JobStatusEnum.FAILED:
            logger.warning("job_retry_skipped", job_id=job_id, status=job.status.value)
            return JobDetailResponse.model_validate(job)

        original_retry_count = job.retry_count
        original_task_id = job.celery_task_id

        repository: Optional[Repository] = None
        original_repository_status: Optional[RepositoryStatusEnum] = None
        if job.repository_id:
            repository = await self._session.get(Repository, job.repository_id)
            if repository:
                original_repository_status = repository.status

        # Reset job state for retry
        job.status = JobStatusEnum.PENDING
        job.retry_count += 1
        job.error_message = None
        job.error_traceback = None
        job.started_at = None
        job.completed_at = None
        job.duration_seconds = None

        if repository:
            repository.status = RepositoryStatusEnum.PENDING

        new_task_id = str(uuid4())
        job.celery_task_id = new_task_id

        await self._session.flush()
        await self._session.refresh(job)

        try:
            self._enqueue_retry_task(job)
        except ValueError as exc:
            error_msg = f"Failed to retry job: {str(exc)}"
            logger.error(
                "job_retry_enqueue_failed",
                job_id=job_id,
                job_type=job.job_type,
                error=error_msg,
            )

            # Restore previous state and persist failure details
            job.status = JobStatusEnum.FAILED
            job.retry_count = original_retry_count
            job.celery_task_id = original_task_id
            job.error_message = error_msg
            if repository and original_repository_status:
                repository.status = original_repository_status

            await self._session.flush()
            await self._session.refresh(job)

            raise ValueError(error_msg) from exc

        logger.info(
            "job_retry_enqueued",
            job_id=job_id,
            job_type=job.job_type,
            task_id=new_task_id,
            retry_count=job.retry_count,
        )

        return JobDetailResponse.model_validate(job)

    def _enqueue_retry_task(self, job: Job) -> None:
        """Enqueue the Celery task associated with the given job."""
        if not job.celery_task_id:
            raise ValueError("Failed to enqueue retry task: Missing Celery task identifier")

        if job.job_type == "sync_repository":
            if not job.repository_id:
                raise ValueError("Failed to enqueue retry task: Repository ID is required for sync_repository job")
            from src.workers.tasks import sync_repository

            sync_repository.apply_async(args=[job.repository_id], task_id=job.celery_task_id)
        elif job.job_type == "parse_file":
            file_id = None
            if job.job_metadata:
                file_id = job.job_metadata.get("file_id")

            if not file_id:
                raise ValueError("Failed to enqueue retry task: file_id missing in job metadata for parse_file job")

            from src.workers.tasks import parse_file_task

            parse_file_task.apply_async(args=[file_id], task_id=job.celery_task_id)
        elif job.job_type == "generate_embeddings":
            chunk_ids = None
            if job.job_metadata:
                chunk_ids = job.job_metadata.get("chunk_ids")

            if not chunk_ids:
                raise ValueError("Failed to enqueue retry task: chunk_ids missing in job metadata for generate_embeddings job")

            from src.workers.tasks import generate_embeddings_task

            generate_embeddings_task.apply_async(args=[chunk_ids], task_id=job.celery_task_id)
        else:
            raise ValueError(f"Failed to enqueue retry task: Unsupported job type '{job.job_type}'")

    async def cancel(self, job_id: int) -> bool:
        """Cancel a pending or running job."""
        job = await self._session.get(Job, job_id)
        if job is None:
            return False
        
        if job.status in [JobStatusEnum.PENDING, JobStatusEnum.RUNNING, JobStatusEnum.RETRYING]:
            job.status = JobStatusEnum.CANCELLED
            await self._session.flush()
            return True
        
        return False

