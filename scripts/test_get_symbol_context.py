
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from src.database.session import get_async_session
from src.database.models import Symbol, Repository
from src.mcp_server.tools.symbols import get_symbol_context

async def main():
    print("Testing get_symbol_context tool...")
    
    async with get_async_session() as session:
        # Find a symbol in repository 65 (or any repo)
        print("Finding a test symbol...")
        result = await session.execute(
            select(Symbol)
            .join(Repository)
            .where(Repository.id == 65)
            .limit(1)
        )
        symbol = result.scalar_one_or_none()
        
        if not symbol:
            print("No symbol found in repository 65. Trying any repository...")
            result = await session.execute(select(Symbol).limit(1))
            symbol = result.scalar_one_or_none()
            
        if not symbol:
            print("No symbols found in database.")
            return
            
        print(f"Found symbol: {symbol.name} (ID: {symbol.id})")
        
        # Test depth=0 (should work)
        print(f"\nTesting depth=0 for symbol {symbol.id}...")
        try:
            result = await get_symbol_context(symbol_id=symbol.id, depth=0)
            print(f"Depth=0 success. Result length: {len(result[0].text)}")
        except Exception as e:
            print(f"Depth=0 failed: {e}")
            
        # Test depth=1 (reported broken)
        print(f"\nTesting depth=1 for symbol {symbol.id}...")
        try:
            result = await get_symbol_context(symbol_id=symbol.id, depth=1)
            if "Failed to get symbol context" in result[0].text:
                print(f"Depth=1 failed with error message: {result[0].text}")
            else:
                print(f"Depth=1 success. Result length: {len(result[0].text)}")
        except Exception as e:
            print(f"Depth=1 raised exception: {e}")

if __name__ == "__main__":
    asyncio.run(main())
