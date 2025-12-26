"""Common FastAPI dependencies."""

from typing import AsyncGenerator

from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import get_db_session as _get_db_session


_limiter = Limiter(key_func=get_remote_address)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session for request scope."""

    async for session in _get_db_session():
        yield session


def get_limiter() -> Limiter:
    """Expose the shared SlowAPI limiter instance."""

    return _limiter


