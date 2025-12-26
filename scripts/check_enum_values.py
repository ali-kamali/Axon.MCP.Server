#!/usr/bin/env python3
"""
Quick script to check current enum values in the database.
"""

import sys
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from src.database.session import engine
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


async def check_enum_values():
    """Check current relationtypeenum values in the database."""
    try:
        async with engine.begin() as conn:
            # Get current enum values
            result = await conn.execute(text("""
                SELECT e.enumlabel 
                FROM pg_enum e
                JOIN pg_type t ON e.enumtypid = t.oid
                WHERE t.typname = 'relationtypeenum'
                ORDER BY e.enumsortorder;
            """))
            
            enum_values = [row[0] for row in result.fetchall()]
            
            print("Current relationtypeenum values:")
            for value in enum_values:
                print(f"  - {value}")
            
            print("\nExpected values:")
            expected = ['CALLS', 'IMPORTS', 'EXPORTS', 'INHERITS', 'IMPLEMENTS', 'USES', 'CONTAINS', 'OVERRIDES', 'REFERENCES']
            for value in expected:
                print(f"  - {value}")
            
            print("\nMissing values:")
            missing = [v for v in expected if v not in enum_values]
            if missing:
                for value in missing:
                    print(f"  - {value}")
            else:
                print("  None - all values are present!")
                
    except Exception as e:
        logger.error(f"Error checking enum values: {e}")
        print(f"Error: {e}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(check_enum_values())
