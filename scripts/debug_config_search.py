"""Debug configuration search for repository 38."""
import asyncio
from sqlalchemy import select, func, cast, String
from src.database.session import get_async_session
from src.database.models import ConfigurationEntry, Symbol, File, Repository
from src.config.enums import SymbolKindEnum


async def debug_config_search():
    async with get_async_session() as session:
        # 1. Check repository exists
        repo_result = await session.execute(
            select(Repository).where(Repository.id == 38)
        )
        repo = repo_result.scalar_one_or_none()
        print(f"\n=== Repository 38 ===")
        print(f"Name: {repo.name if repo else 'NOT FOUND'}")
        
        if not repo:
            print("Repository 38 not found!")
            return
        
        # 2. Check ConfigurationEntry table
        config_count = await session.execute(
            select(func.count(ConfigurationEntry.id)).where(
                ConfigurationEntry.repository_id == 38
            )
        )
        count = config_count.scalar()
        print(f"\n=== ConfigurationEntry Table ===")
        print(f"Total entries: {count}")
        
        if count > 0:
            # Show first 5 entries
            config_sample = await session.execute(
                select(ConfigurationEntry)
                .where(ConfigurationEntry.repository_id == 38)
                .limit(5)
            )
            print("\nSample entries:")
            for entry in config_sample.scalars():
                print(f"  - {entry.config_key} = {entry.config_value} ({entry.file_path})")
        
        # 3. Check Symbol table for configuration symbols
        symbol_count = await session.execute(
            select(func.count(Symbol.id))
            .select_from(Symbol)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == 38,
                cast(Symbol.structured_docs['type'], String) == 'configuration'
            )
        )
        count = symbol_count.scalar()
        print(f"\n=== Symbol Table (Configuration) ===")
        print(f"Total symbols with type='configuration': {count}")
        
        if count > 0:
            # Show first 5
            symbol_sample = await session.execute(
                select(Symbol, File)
                .join(File, Symbol.file_id == File.id)
                .where(
                    File.repository_id == 38,
                    cast(Symbol.structured_docs['type'], String) == 'configuration'
                )
                .limit(5)
            )
            print("\nSample symbols:")
            for symbol, file in symbol_sample:
                print(f"  - {symbol.name} (kind={symbol.kind.value}, file={file.path})")
                if symbol.structured_docs:
                    print(f"    structured_docs: {symbol.structured_docs}")
        
        # 4. Check files that should contain configuration
        config_files = await session.execute(
            select(File)
            .where(
                File.repository_id == 38,
                (File.path.ilike('%appsettings%')) | 
                (File.path.ilike('%web.config')) |
                (File.path.ilike('%.config'))
            )
        )
        files = config_files.scalars().all()
        print(f"\n=== Configuration Files ===")
        print(f"Found {len(files)} potential config files:")
        for f in files:
            print(f"  - {f.path} (language={f.language.value})")


if __name__ == "__main__":
    asyncio.run(debug_config_search())
