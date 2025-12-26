#!/usr/bin/env python3
"""
Check the current status of the enum values in the database.
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


async def check_enum_status():
    """Check the current enum status."""
    async with engine.begin() as conn:
        # Check enum type and values
        result = await conn.execute(text("""
            SELECT e.enumlabel 
            FROM pg_enum e
            JOIN pg_type t ON e.enumtypid = t.oid
            WHERE t.typname = 'sourcecontrolproviderenum'
            ORDER BY e.enumsortorder;
        """))
        enum_values = [row[0] for row in result.fetchall()]
        
        print(f"Current enum values in database: {enum_values}")
        
        # Check actual data in repositories table
        result = await conn.execute(text("""
            SELECT DISTINCT provider::text as provider_value
            FROM repositories;
        """))
        data_values = [row[0] for row in result.fetchall()]
        
        print(f"Actual provider values in repositories table: {data_values}")
        
        # Check column type
        result = await conn.execute(text("""
            SELECT data_type, udt_name
            FROM information_schema.columns
            WHERE table_name = 'repositories' AND column_name = 'provider';
        """))
        col_info = result.fetchone()
        print(f"Column type: {col_info}")
        
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(check_enum_status())

