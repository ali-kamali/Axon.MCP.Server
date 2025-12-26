"""Seed database with test data."""
import asyncio

from src.database.session import get_async_session
from src.database.models import Repository
from src.config.enums import RepositoryStatusEnum


async def seed_test_repository() -> None:
    """Create a test repository."""
    async with get_async_session() as session:
        test_repo = Repository(
            gitlab_project_id=12345,
            name="test-repository",
            path_with_namespace="group/test-repository",
            url="https://gitlab.com/group/test-repository.git",
            default_branch="main",
            description="Test repository for development",
            status=RepositoryStatusEnum.PENDING,
        )
        session.add(test_repo)
        await session.flush()
        print(f"Created test repository with ID: {test_repo.id}")


if __name__ == "__main__":
    asyncio.run(seed_test_repository())


