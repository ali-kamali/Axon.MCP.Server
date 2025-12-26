"""Repository locking mechanism to prevent concurrent syncs."""

from typing import Optional
from contextlib import asynccontextmanager
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

from src.database.models import Repository
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
        
        Uses database-level locking to prevent concurrent modifications.
        
        Args:
            repository_id: Repository to lock
            timeout_seconds: Lock timeout in seconds
            
        Yields:
            bool: True if lock acquired
        """
        acquired = False
        
        try:
            # Try to acquire lock using PostgreSQL advisory lock
            # pg_try_advisory_lock returns true if lock acquired
            from sqlalchemy import text
            
            result = await self.session.execute(
                text(f"SELECT pg_try_advisory_lock({repository_id})")
            )
            acquired = result.scalar()
            
            if acquired:
                logger.info("repository_lock_acquired", repository_id=repository_id)
            else:
                logger.warning("repository_lock_failed", repository_id=repository_id)
            
            yield acquired
            
        finally:
            # Release lock
            if acquired:
                await self.session.execute(
                    text(f"SELECT pg_advisory_unlock({repository_id})")
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
        from sqlalchemy import text
        
        # Check if lock exists for this repository
        result = await self.session.execute(
            text(f"SELECT pg_try_advisory_lock({repository_id})")
        )
        can_acquire = result.scalar()
        
        if can_acquire:
            # We just acquired it, release immediately
            await self.session.execute(
                text(f"SELECT pg_advisory_unlock({repository_id})")
            )
            return False
        
        return True

