"""Debug script to check library projects in repository 38."""
import asyncio
from sqlalchemy import select, func
from src.database.session import get_async_session
from src.database.models import Project, Symbol

async def check_projects():
    async with get_async_session() as session:
        # Get all projects
        result = await session.execute(
            select(Project)
            .where(Project.repository_id == 38)
            .order_by(Project.name)
        )
        projects = result.scalars().all()
        
        print(f"\n=== Projects in Repository 38 ===\n")
        for project in projects:
            # Count symbols
            symbol_count_result = await session.execute(
                select(func.count(Symbol.id))
                .where(Symbol.project_id == project.id)
            )
            symbol_count = symbol_count_result.scalar() or 0
            
            print(f"📦 {project.name}")
            print(f"   Output Type: {project.output_type}")
            print(f"   Symbols: {symbol_count}")
            print(f"   Framework: {project.target_framework}")
            print()

if __name__ == "__main__":
    asyncio.run(check_projects())
