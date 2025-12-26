"""Pytest configuration and shared fixtures."""

import os
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database.models import Base

# Ensure src/ is importable during tests
_project_root = Path(__file__).parent.parent
_src_path = _project_root / "src"
os.environ.setdefault("PYTHONPATH", str(_project_root))


# Test database URL (use a separate test database)
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/axon_test"
)


@pytest.fixture(scope="session")
def event_loop_policy():
    """Set event loop policy for Windows compatibility."""
    import asyncio
    import sys
    
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest_asyncio.fixture(scope="function")
async def async_engine():
    """Create async engine for tests."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Drop all tables after tests
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create async session for tests.
    
    This fixture provides a clean database session for each test.
    All changes are rolled back after the test completes.
    """
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    
    async with async_session_maker() as session:
        # Start a transaction
        await session.begin()
        
        try:
            yield session
        finally:
            # Rollback any changes made during the test
            await session.rollback()
            await session.close()


@pytest.fixture(scope="session")
def anyio_backend():
    """Configure anyio backend for async tests."""
    return "asyncio"


@pytest.fixture
def sample_code_csharp():
    """Sample C# code for testing."""
    return '''
namespace TestNamespace
{
    /// <summary>
    /// Test class documentation
    /// </summary>
    public class TestClass
    {
        public void TestMethod(string param)
        {
            Console.WriteLine(param);
        }
    }
}
'''


@pytest.fixture
def sample_code_typescript():
    """Sample TypeScript code for testing."""
    return '''
interface User {
    id: number;
    name: string;
}

/**
 * Get user by ID
 * @param id User ID
 * @returns User object
 */
function getUser(id: number): User {
    return { id, name: "Test" };
}
'''


@pytest_asyncio.fixture
async def sample_repository(async_session):
    """Create sample repository."""
    from src.database.models import Repository
    from src.config.enums import RepositoryStatusEnum
    
    repo = Repository(
        gitlab_project_id=12345,
        name="test-repo",
        path_with_namespace="test/repo",
        url="https://example.com/test/repo.git",
        default_branch="main",
        status=RepositoryStatusEnum.PENDING
    )
    
    async_session.add(repo)
    await async_session.commit()
    await async_session.refresh(repo)
    
    return repo


# Alias for backward compatibility
@pytest_asyncio.fixture
async def db_session(async_session):
    """Alias for async_session for backward compatibility."""
    return async_session