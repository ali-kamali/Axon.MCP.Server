"""Initialize database and create tables."""
import asyncio
import sqlalchemy as sa

from sqlalchemy.ext.asyncio import create_async_engine

from src.database.models import Base
from src.config.settings import settings


def _ensure_asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def init_db() -> None:
    """Create pgvector extension and all tables."""
    engine = create_async_engine(
        _ensure_asyncpg_url(settings.database_url),
        echo=settings.database_echo,
    )

    async with engine.begin() as conn:
        # Enable pgvector extension
        await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

        # Create all tables
        await conn.run_sync(Base.metadata.create_all)

    await engine.dispose()
    print("Database initialized successfully!")


if __name__ == "__main__":
    asyncio.run(init_db())


