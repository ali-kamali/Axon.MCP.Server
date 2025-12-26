"""Debug script to check why libraries aren't detected."""
import asyncio
from sqlalchemy import select, func
from src.database.session import get_async_session
from src.database.models import Project, Symbol
from src.config.settings import settings

async def debug_library_detection():
    print(f"\n=== Library Detection Debug ===")
    print(f"DETECT_LIBRARY_SERVICES: {settings.detect_library_services}")
    print(f"MIN_LIBRARY_SYMBOLS: {settings.min_library_symbols}\n")
    
    async with get_async_session() as session:
        # Get all Library type projects
        result = await session.execute(
            select(Project)
            .where(
                Project.repository_id == 38,
                Project.output_type == "Library"
            )
            .order_by(Project.name)
        )
        library_projects = result.scalars().all()
        
        if not library_projects:
            print("❌ NO LIBRARY PROJECTS FOUND!")
            print("   Possible reasons:")
            print("   1. Projects don't have output_type='Library' in database")
            print("   2. .csproj files don't specify <OutputType>Library</OutputType>")
            return
        
        print(f"Found {len(library_projects)} library projects:\n")
        
        for project in library_projects:
            # Count symbols
            symbol_result = await session.execute(
                select(func.count(Symbol.id))
                .where(Symbol.project_id == project.id)
            )
            symbol_count = symbol_result.scalar() or 0
            
            # Detect layer
            name_lower = project.name.lower()
            layer = "Unknown"
            if "domain" in name_lower:
                layer = "Domain"
            elif "application" in name_lower:
                layer = "Application"
            elif "infrastructure" in name_lower or "persistence" in name_lower:
                layer = "Infrastructure"
            elif "shared" in name_lower or "common" in name_lower:
                layer = "Shared"
            elif "core" in name_lower:
                layer = "Core"
            
            # Check if would be detected
            meets_threshold = symbol_count >= settings.min_library_symbols
            status = "✅ DETECTED" if meets_threshold else f"❌ TOO FEW SYMBOLS (need {settings.min_library_symbols})"
            
            print(f"{status}")
            print(f"  📦 {project.name}")
            print(f"  🏷️  Layer: {layer}")
            print(f"  📊 Symbols: {symbol_count}")
            print(f"  🎯 Framework: {project.target_framework}")
            print()

if __name__ == "__main__":
    asyncio.run(debug_library_detection())
