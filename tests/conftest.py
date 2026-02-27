import os
import sys
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Ensure src/ is importable during tests
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Set environment variables for testing BEFORE importing any app code
# This ensures that src.database.session picks up the test database URL
os.environ["ENVIRONMENT"] = "testing"

# In CI environments, DATABASE_URL is often set to the correct test database service.
# Locally, we prefer TEST_DATABASE_URL or the default axon_test.
effective_db_url = (
    os.getenv("DATABASE_URL") or 
    os.getenv("TEST_DATABASE_URL") or 
    "postgresql+asyncpg://postgres:postgres@localhost:5432/axon_test"
)
os.environ["DATABASE_URL"] = effective_db_url

# Disable SSL for tests
os.environ["DATABASE_SSL"] = "False"

from src.database.models import Base
from src.database.session import engine as global_engine


@pytest.fixture(scope="session")
def event_loop_policy():
    """Set event loop policy for Windows compatibility."""
    import asyncio
    import sys
    
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest_asyncio.fixture(scope="function")
async def async_engine():
    """Ensure database tables are created for tests.

    If no PostgreSQL test database is reachable, skip DB-dependent tests
    instead of hard-failing the entire suite.
    """
    import sqlalchemy as sa

    try:
        # Create pgvector extension and tables using the global engine
        # to ensure all code under test uses the same connection pool
        async with global_engine.begin() as conn:
            # Enable pgvector extension first
            await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
            # Then create all tables
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        pytest.skip(f"PostgreSQL test database unavailable: {exc}")

    try:
        yield global_engine
    finally:
        # Drop all tables after tests for clean state
        async with global_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

        # CRITICAL: Dispose of the engine to clear the connection pool.
        # This prevents "Future attached to a different loop" errors in asyncpg
        # when the next test starts with a new event loop.
        await global_engine.dispose()


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
        clone_url="https://example.com/test/repo.git",
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