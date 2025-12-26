"""Repository management endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status, WebSocket, WebSocketDisconnect
import redis.asyncio as redis
import json
from src.config.settings import settings
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db_session
from src.api.schemas.repositories import (
    RepositoryCreate,
    RepositoryResponse,
    RepositorySyncResponse,
    GitLabDiscoveryResponse,
    AzureDevOpsDiscoveryResponse,
    BulkRepositoryAddRequest,
    BulkRepositoryAddResponse,
    BulkRepositoryRemoveRequest,
    BulkRepositoryRemoveResponse,
    BulkRepositorySyncRequest,
    BulkRepositorySyncResponse,
    PaginatedResponse,
)
from src.api.services.repository_service import RepositoryService
from src.api.services.sample_service import SampleService
from src.api.schemas.samples import RepositorySamples
from src.api.services.statistics_service import StatisticsService
from src.api.schemas.statistics import RepositoryStatistics
from src.api.services.job_service import JobService
from src.api.schemas.jobs import JobResponse
from src.api.auth import get_current_user


router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/repositories", response_model=PaginatedResponse[RepositoryResponse])
async def list_repositories(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[RepositoryResponse]:
    """Return a paginated list of tracked repositories."""

    service = RepositoryService(session)
    items, total = await service.list(offset=skip, limit=limit)
    return PaginatedResponse(items=items, total=total, limit=limit, offset=skip)


@router.post("/repositories", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
async def create_repository(
    payload: RepositoryCreate,
    session: AsyncSession = Depends(get_db_session),
) -> RepositoryResponse:
    """Create a repository record and enqueue its first sync."""

    service = RepositoryService(session)
    try:
        repository = await service.create(payload)
    except IntegrityError as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Failed to create repository: Repository already exists"
        ) from exc

    await service.trigger_sync(repository.id)
    refreshed = await service.get(repository.id)
    assert refreshed is not None
    return refreshed


@router.get("/repositories/{repository_id}", response_model=RepositoryResponse)
async def get_repository(
    repository_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> RepositoryResponse:
    """Retrieve repository details."""

    service = RepositoryService(session)
    repository = await service.get(repository_id)
    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed to get repository: Repository with ID {repository_id} not found"
        )
    return repository


@router.get("/repositories/{repository_id}/stats", response_model=RepositoryStatistics)
async def get_repository_stats(
    repository_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> RepositoryStatistics:
    """Get statistics for a specific repository."""
    service = StatisticsService(session)
    try:
        return await service.get_repository_stats(repository_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/repositories/{repository_id}/sync-history", response_model=PaginatedResponse[JobResponse])
async def get_repository_sync_history(
    repository_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[JobResponse]:
    """Get sync history (jobs) for a repository."""
    
    # Verify repository exists
    repo_service = RepositoryService(session)
    repository = await repo_service.get(repository_id)
    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository with ID {repository_id} not found"
        )

    job_service = JobService(session)
    items, total = await job_service.list(
        offset=offset, 
        limit=limit, 
        repository_id=repository_id
    )
    
    return PaginatedResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/repositories/{repository_id}/samples", response_model=RepositorySamples)
async def get_repository_samples(
    repository_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> RepositorySamples:
    """Get 5 random samples of each entity type for a repository."""
    
    # Verify repository exists first
    repo_service = RepositoryService(session)
    repository = await repo_service.get(repository_id)
    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository with ID {repository_id} not found"
        )
    
    sample_service = SampleService(session)
    samples = await sample_service.get_repository_samples(repository_id)
    return samples


@router.post("/repositories/{repository_id}/sync", response_model=RepositorySyncResponse)
async def trigger_repository_sync(
    repository_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> RepositorySyncResponse:
    """Trigger a manual repository synchronization."""

    service = RepositoryService(session)
    try:
        response = await service.trigger_sync(repository_id)
    except ValueError as exc:  # repository missing
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed to sync repository: Repository with ID {repository_id} not found"
        ) from exc

    return response


@router.delete("/repositories/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repository(
    repository_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Delete a single repository and all associated data."""

    service = RepositoryService(session)
    repository = await service.get(repository_id)
    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Failed to delete repository: Repository with ID {repository_id} not found"
        )
    
    # Use the bulk remove method with a single ID
    response = await service.bulk_remove_repositories([repository_id])
    
    if response.failed_count > 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete repository: {response.errors[0]}"
        )


@router.get("/repositories/discover/{group_id}", response_model=GitLabDiscoveryResponse)
async def discover_gitlab_projects(
    group_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> GitLabDiscoveryResponse:
    """
    Discover all projects in a GitLab group and check which are already tracked.
    
    Args:
        group_id: GitLab group ID or path (e.g., "mycompany" or "123")
    
    Returns:
        List of all projects with tracking status
    """
    service = RepositoryService(session)
    try:
        response = await service.discover_gitlab_projects(group_id)
        return response
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to discover GitLab projects: {str(exc)}",
        ) from exc


@router.get("/repositories/discover/azuredevops/{project_name}", response_model=AzureDevOpsDiscoveryResponse)
async def discover_azuredevops_repositories(
    project_name: str,
    session: AsyncSession = Depends(get_db_session),
) -> AzureDevOpsDiscoveryResponse:
    """
    Discover all repositories in an Azure DevOps project and check which are already tracked.
    
    Args:
        project_name: Azure DevOps project name
    
    Returns:
        List of all repositories with tracking status
    """
    service = RepositoryService(session)
    try:
        response = await service.discover_azuredevops_repositories(project_name)
        return response
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to discover Azure DevOps repositories: {str(exc)}",
        ) from exc


@router.post("/repositories/bulk-add", response_model=BulkRepositoryAddResponse)
async def bulk_add_repositories(
    payload: BulkRepositoryAddRequest,
    session: AsyncSession = Depends(get_db_session),
) -> BulkRepositoryAddResponse:
    """
    Add multiple repositories in bulk.
    
    Skips repositories that are already tracked.
    """
    service = RepositoryService(session)
    response = await service.bulk_add_repositories(payload.repositories)
    return response


@router.post("/repositories/bulk-remove", response_model=BulkRepositoryRemoveResponse)
async def bulk_remove_repositories(
    payload: BulkRepositoryRemoveRequest,
    session: AsyncSession = Depends(get_db_session),
) -> BulkRepositoryRemoveResponse:
    """
    Remove multiple repositories in bulk.
    
    This will delete the repository records and all associated data.
    Uses POST method as it requires a request body with repository IDs.
    """
    service = RepositoryService(session)
    response = await service.bulk_remove_repositories(payload.repository_ids)
    return response


@router.delete("/repositories/bulk-delete", response_model=BulkRepositoryRemoveResponse)
async def bulk_delete_repositories(
    payload: BulkRepositoryRemoveRequest,
    session: AsyncSession = Depends(get_db_session),
) -> BulkRepositoryRemoveResponse:
    """
    Remove multiple repositories in bulk (DELETE alias).
    
    This is an alias for bulk-remove that accepts DELETE method.
    This will delete the repository records and all associated data.
    """
    service = RepositoryService(session)
    response = await service.bulk_remove_repositories(payload.repository_ids)
    return response


@router.post("/repositories/bulk-sync", response_model=BulkRepositorySyncResponse)
async def bulk_sync_repositories(
    payload: BulkRepositorySyncRequest,
    session: AsyncSession = Depends(get_db_session),
) -> BulkRepositorySyncResponse:
    """
    Sync multiple repositories in bulk.
    
    This will trigger synchronization tasks for all specified repositories.
    Returns the job IDs for tracking the sync progress.
    """
    service = RepositoryService(session)
    response = await service.bulk_sync_repositories(payload.repository_ids)
    return response


@router.websocket("/repositories/{repository_id}/logs")
async def websocket_repository_logs(
    websocket: WebSocket,
    repository_id: int,
):
    """Stream live logs for a repository sync using Redis Streams."""
    await websocket.accept()
    
    redis_client = redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    stream_key = f"repository_logs_stream:{repository_id}"
    last_id = "0-0"
    
    try:
        while True:
            # Read new messages from the stream
            # block=1000 means wait up to 1 second for new messages
            streams = await redis_client.xread(
                {stream_key: last_id},
                count=100,
                block=1000
            )
            
            if streams:
                for stream_name, messages in streams:
                    for message_id, fields in messages:
                        if "data" in fields:
                            await websocket.send_text(fields["data"])
                        last_id = message_id
            
            # Small sleep to prevent tight loop if xread returns immediately (shouldn't happen with block)
            # But strictly speaking, await xread yields control.
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        # Log the error but don't crash the server
        print(f"Error in websocket_repository_logs: {e}")
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
    finally:
        await redis_client.close()
