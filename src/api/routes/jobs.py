"""Job management endpoints."""

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from src.api.dependencies import get_db_session
from src.api.schemas.jobs import JobDetailResponse, JobResponse
from src.api.services.job_service import JobService
from src.config.enums import JobStatusEnum
from src.api.auth import get_current_user


router = APIRouter(dependencies=[Depends(get_current_user)])


class LinkMicroservicesRequest(BaseModel):
    """Request model for linking microservices."""
    repository_ids: Optional[List[int]] = None


class PaginatedJobResponse:
    """Paginated job response."""

    def __init__(self, items: list[JobResponse], total: int, limit: int, offset: int):
        self.items = items
        self.total = total
        self.limit = limit
        self.offset = offset


@router.get("/jobs")
async def list_jobs(
    status_filter: Optional[JobStatusEnum] = Query(None, alias="status"),
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Return a paginated list of jobs with optional status filter."""
    service = JobService(session)
    jobs, total = await service.list(offset=offset, limit=limit, status=status_filter)
    
    return {
        "items": jobs,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
async def get_job(
    job_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> JobDetailResponse:
    """Get detailed information about a specific job."""
    service = JobService(session)
    job = await service.get(job_id)
    
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    
    return job


@router.post("/jobs/{job_id}/retry", response_model=JobDetailResponse)
async def retry_job(
    job_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> JobDetailResponse:
    """Retry a failed job."""
    service = JobService(session)
    try:
        job = await service.retry(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed to retry job: Job with ID {job_id} not found"
        )
    
    return job


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_job(
    job_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Cancel a pending or running job."""
    service = JobService(session)
    success = await service.cancel(job_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job not found or cannot be cancelled",
        )


@router.post("/jobs/link-microservices", status_code=status.HTTP_202_ACCEPTED)
async def trigger_link_microservices(
    request: LinkMicroservicesRequest = None,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    Trigger the microservices linking task (Phase 3: The Linker).
    
    This task:
    1. Parses gateway configurations (Ocelot, Nginx) to understand routing
    2. Links frontend API calls to backend endpoints using fuzzy matching
    3. Links event publishers to subscribers across repositories
    
    Args:
        request: Optional request body with repository_ids to limit scope
        
    Returns:
        Task information with task_id for tracking
    """
    from src.workers.tasks import link_microservices
    
    repository_ids = request.repository_ids if request else None
    
    # Trigger the Celery task
    task = link_microservices.delay(repository_ids=repository_ids)
    
    return {
        "message": "Microservices linking task started",
        "task_id": task.id,
        "repository_ids": repository_ids,
        "status": "pending",
    }


@router.post("/jobs/link-repository/{repository_id}", status_code=status.HTTP_202_ACCEPTED)
async def trigger_link_repository(
    repository_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    Trigger linking for a single repository.
    
    This is a convenience endpoint for linking a single repository after sync.
    
    Args:
        repository_id: Repository ID to link
        
    Returns:
        Task information with task_id for tracking
    """
    from src.workers.tasks import link_repository
    from sqlalchemy import select
    from src.database.models import Repository
    
    # Verify repository exists
    result = await session.execute(
        select(Repository).where(Repository.id == repository_id)
    )
    repo = result.scalar_one_or_none()
    
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository with ID {repository_id} not found"
        )
    
    # Trigger the Celery task
    task = link_repository.delay(repository_id=repository_id)
    
    return {
        "message": f"Linking task started for repository {repo.name}",
        "task_id": task.id,
        "repository_id": repository_id,
        "repository_name": repo.name,
        "status": "pending",
    }

