"""Worker management endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db_session
from src.api.schemas.workers import WorkerResponse
from src.api.services.worker_service import WorkerService
from src.api.auth import get_current_user


router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/workers", response_model=list[WorkerResponse])
async def list_workers(
    session: AsyncSession = Depends(get_db_session),
) -> list[WorkerResponse]:
    """Return a list of all workers."""
    service = WorkerService(session)
    return await service.list()

