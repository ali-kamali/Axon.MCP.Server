"""Repository locking mechanism to prevent concurrent syncs."""

import asyncio
from contextlib import asynccontextmanager
from time import monotonic

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class RepositoryLock:
    """Lock mechanism for repository operations."""

    def __init__(self, session: AsyncSession):
        """
        Initialize repository lock.

        Args:
            session: Database session
        """
        self.session = session

    @asynccontextmanager
    async def acquire_lock(
        self,
        repository_id: int,
        timeout_seconds: int = 3600
    ):
        """
        Acquire lock on repository.

        Uses PostgreSQL advisory locking to prevent concurrent modifications.

        Args:
            repository_id: Repository to lock
            timeout_seconds: Maximum wait time in seconds for lock acquisition

        Yields:
            bool: True if lock acquired
        """
        acquired = False
        deadline = monotonic() + max(timeout_seconds, 0)

        try:
            while True:
                result = await self.session.execute(
                    text("SELECT pg_try_advisory_lock(:lock_id)"),
                    {"lock_id": repository_id},
                )
                acquired = bool(result.scalar())
                if acquired:
                    logger.info("repository_lock_acquired", repository_id=repository_id)
                    break

                if monotonic() >= deadline:
                    logger.warning(
                        "repository_lock_failed",
                        repository_id=repository_id,
                        timeout_seconds=timeout_seconds,
                    )
                    break

                await asyncio.sleep(0.1)

            yield acquired

        finally:
            if acquired:
                await self.session.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": repository_id},
                )
                logger.info("repository_lock_released", repository_id=repository_id)

    async def is_locked(self, repository_id: int) -> bool:
        """
        Check if repository is currently locked.

        Args:
            repository_id: Repository to check

        Returns:
            True if locked
        """
        result = await self.session.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": repository_id},
        )
        can_acquire = bool(result.scalar())

        if can_acquire:
            await self.session.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": repository_id},
            )
            return False

        return True
