"""Worker service utilities."""

from __future__ import annotations

from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.workers import WorkerResponse
from src.database.models import Worker
from src.utils.logging_config import get_logger


logger = get_logger(__name__)


class WorkerService:
    """Encapsulates worker CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> List[WorkerResponse]:
        """List all workers."""
        stmt = select(Worker).order_by(Worker.last_heartbeat_at.desc().nullslast())
        result = await self._session.execute(stmt)
        workers = result.scalars().all()
        return [WorkerResponse.model_validate(worker) for worker in workers]

