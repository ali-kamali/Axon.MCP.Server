
import asyncio
import sys
import os
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load .env file
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Patch DATABASE_URL for local execution (if it points to docker service)
db_url = os.getenv('DATABASE_URL')
if db_url and '@postgres:' in db_url:
    os.environ['DATABASE_URL'] = db_url.replace('@postgres:', '@localhost:')
    print(f"Patched DATABASE_URL to use localhost")

from src.database.session import get_async_session
from src.database.models import Repository, Symbol, Dependency, File
from src.mcp_server.tools.repository import list_dependencies
from sqlalchemy import select, func, cast, String

async def main():
    async with get_async_session() as session:
        # 1. List Repositories
        print("--- Repositories ---")
        result = await session.execute(select(Repository))
        repos = result.scalars().all()
        for repo in repos:
            print(f"Repo: {repo.name} (ID: {repo.id})")
            
            # 2. Call list_dependencies
            print(f"\n  Calling list_dependencies({repo.id})...")
            deps_output = await list_dependencies(repo.id)
            print(f"  Output: {deps_output[0].text[:200]}...") # Print first 200 chars
            
            # 3. Check Dependency Table
            print(f"\n  Checking 'dependencies' table for Repo {repo.id}...")
            result = await session.execute(select(func.count(Dependency.id)).where(Dependency.repository_id == repo.id))
            dep_count = result.scalar()
            print(f"  Found {dep_count} records in 'dependencies' table.")
            
            if dep_count > 0:
                result = await session.execute(select(Dependency).where(Dependency.repository_id == repo.id).limit(5))
                deps = result.scalars().all()
                for d in deps:
                    print(f"    - {d.package_name} ({d.dependency_type})")

            # 4. Check Symbol Table
            print(f"\n  Checking 'symbols' table for Repo {repo.id} (nuget/npm)...")
            # Try to replicate the query in list_dependencies
            # Note: casting JSON to String might be DB specific (SQLite vs Postgres)
            # We'll just fetch all symbols and filter in python to be sure
            
            # Fetch all symbols with structured_docs
            result = await session.execute(select(Symbol).join(File).where(File.repository_id == repo.id))
            symbols = result.scalars().all()
            
            pkg_symbols = []
            for s in symbols:
                if s.structured_docs and isinstance(s.structured_docs, dict):
                    dtype = s.structured_docs.get('type')
                    if dtype in ['nuget_package', 'npm_package']:
                        pkg_symbols.append(s)
            
            print(f"  Found {len(pkg_symbols)} symbols with type nuget_package/npm_package.")
            for s in pkg_symbols[:5]:
                print(f"    - {s.name} ({s.structured_docs.get('type')})")

if __name__ == "__main__":
    asyncio.run(main())
