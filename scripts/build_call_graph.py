"""Build call graph relationships for repositories."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.session import AsyncSessionLocal
from src.extractors.call_graph_builder import CallGraphBuilder
from src.database.models import Repository
from sqlalchemy import select
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


async def build_call_graph_for_repository(repository_id: int):
    """Build call graph for a specific repository."""
    async with AsyncSessionLocal() as session:
        # Get repository info
        result = await session.execute(
            select(Repository).where(Repository.id == repository_id)
        )
        repo = result.scalar_one_or_none()
        
        if not repo:
            logger.error(f"Repository {repository_id} not found")
            return
        
        logger.info(f"Building call graph for repository: {repo.name}")
        
        builder = CallGraphBuilder(session)
        relationships_created = await builder.build_call_relationships(repository_id)
        
        logger.info(f"✅ Created {relationships_created} CALLS relationships for {repo.name}")
        print(f"\n✅ Successfully created {relationships_created} CALLS relationships for '{repo.name}'")


async def build_call_graph_for_all():
    """Build call graph for all repositories."""
    async with AsyncSessionLocal() as session:
        # Get all repositories
        result = await session.execute(select(Repository))
        repos = result.scalars().all()
        
        if not repos:
            logger.warning("No repositories found")
            print("⚠️  No repositories found in database")
            return
        
        print(f"\nFound {len(repos)} repositories:")
        for repo in repos:
            print(f"  - [{repo.id}] {repo.name} ({repo.total_symbols} symbols)")
        
        print("\nBuilding call graphs...\n")
        
        total_relationships = 0
        for repo in repos:
            logger.info(f"Processing repository: {repo.name}")
            print(f"📊 Processing: {repo.name}...")
            
            builder = CallGraphBuilder(session)
            relationships_created = await builder.build_call_relationships(repo.id)
            total_relationships += relationships_created
            
            print(f"   ✅ Created {relationships_created} CALLS relationships\n")
        
        print(f"\n🎉 Total CALLS relationships created: {total_relationships}")


async def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        # Build for specific repository
        try:
            repo_id = int(sys.argv[1])
            await build_call_graph_for_repository(repo_id)
        except ValueError:
            print("❌ Invalid repository ID. Please provide a number.")
            sys.exit(1)
    else:
        # Build for all repositories
        await build_call_graph_for_all()


if __name__ == "__main__":
    print("=" * 60)
    print("Call Graph Builder")
    print("=" * 60)
    asyncio.run(main())
