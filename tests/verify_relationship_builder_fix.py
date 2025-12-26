
import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.extractors.relationship_builder import RelationshipBuilder
from src.database.models import Symbol
from src.config.enums import SymbolKindEnum

async def test_relationship_builder_none_type():
    print("Testing RelationshipBuilder with None type parameter...")
    
    # Mock session
    session = AsyncMock()
    builder = RelationshipBuilder(session)
    
    # Create symbol with None type parameter
    # This simulates the condition that caused the crash
    sym1 = Symbol(
        id=1, 
        name="Process", 
        kind=SymbolKindEnum.METHOD, 
        return_type="void", 
        parameters=[
            {"name": "p1", "type": "string"},
            {"name": "p2", "type": None} # This caused the crash
        ]
    )
    
    symbols = [sym1]
    symbol_index = {}
    
    # Mock _resolve_type
    builder._resolve_type = MagicMock(return_value=[])
    
    try:
        count = await builder._build_reference_relationships(symbols, symbol_index)
        print(f"Success! Processed {count} relationships.")
    except AttributeError as e:
        print(f"FAILED: Caught expected error: {e}")
        if "'NoneType' object has no attribute 'split'" in str(e):
            print("Confirmed: This is the error we are fixing.")
        raise
    except Exception as e:
        print(f"FAILED: Caught unexpected error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(test_relationship_builder_none_type())
