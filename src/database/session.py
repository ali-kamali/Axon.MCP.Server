from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config.settings import settings


def _ensure_asyncpg_url(url: str) -> str:
    """Ensure database URL uses asyncpg driver for async engine."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


# Create async engine
connect_args = {
    "server_settings": {"application_name": "axon_mcp_server"},
}

if settings.environment == "production":
    connect_args["ssl"] = True


engine = create_async_engine(
    _ensure_asyncpg_url(settings.database_url),
    echo=settings.database_echo,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout=settings.database_pool_timeout,
    pool_pre_ping=True,  # Enable connection health checks
    pool_recycle=3600,  # Recycle connections after 1 hour
    connect_args=connect_args,
)

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get async database session with automatic commit/rollback.

    Usage:
        async with get_async_session() as session:
            # Use session
            pass
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_readonly_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get read-only async database session (no commit).
    
    Use this for SELECT queries to avoid unnecessary transaction commits 
    and improve performance/concurrency.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            # No commit for read-only
        except Exception:
            # No rollback needed effectively, but good practice if something modified state despite intent
            await session.rollback()
            raise


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions."""
    async with get_async_session() as session:
        yield session
