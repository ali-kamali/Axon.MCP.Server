#!/usr/bin/env python3
"""
Migration to add missing OVERRIDES and REFERENCES values to relationtypeenum.

This is a dedicated migration to ensure the enum has all required values.
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


async def add_missing_relation_type_values() -> bool:
    """
    Add OVERRIDES and REFERENCES to relationtypeenum if they don't exist.
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        logger.info(
            "auto_migration_started",
            migration="add_missing_relation_type_values"
        )
        
        async with engine.begin() as conn:
            # Check if relationtypeenum exists
            type_check = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_type WHERE typname = 'relationtypeenum'
                );
            """))
            
            if not type_check.scalar():
                logger.info(
                    "migration_skipped",
                    reason="relationtypeenum type does not exist yet",
                    migration="add_missing_relation_type_values"
                )
                return True
            
            # Get current enum values
            enum_check = await conn.execute(text("""
                SELECT enumlabel 
                FROM pg_enum 
                WHERE enumtypid = (
                    SELECT oid 
                    FROM pg_type 
                    WHERE typname = 'relationtypeenum'
                )
                ORDER BY enumsortorder;
            """))
            
            existing_values = [row[0] for row in enum_check.fetchall()]
            
            logger.info(
                "current_enum_values",
                migration="add_missing_relation_type_values",
                values=existing_values
            )
            
            # Values we need to add
            required_values = ['OVERRIDES', 'REFERENCES']
            missing_values = [v for v in required_values if v not in existing_values]
            
            if not missing_values:
                logger.info(
                    "migration_not_needed",
                    migration="add_missing_relation_type_values",
                    message="All required values already exist"
                )
                return True
            
            logger.info(
                "adding_missing_values",
                migration="add_missing_relation_type_values",
                missing_values=missing_values
            )
            
            # Add each missing value
            for value in missing_values:
                try:
                    await conn.execute(text(f"""
                        ALTER TYPE relationtypeenum ADD VALUE '{value}';
                    """))
                    logger.info(
                        "added_enum_value",
                        enum_type="relationtypeenum",
                        value=value
                    )
                except Exception as e:
                    # If it already exists (race condition), that's fine
                    if 'already exists' in str(e).lower():
                        logger.info(
                            "enum_value_already_exists",
                            enum_type="relationtypeenum",
                            value=value
                        )
                    else:
                        raise
            
            # Verify the values were added
            verify_result = await conn.execute(text("""
                SELECT enumlabel 
                FROM pg_enum 
                WHERE enumtypid = (
                    SELECT oid 
                    FROM pg_type 
                    WHERE typname = 'relationtypeenum'
                )
                ORDER BY enumsortorder;
            """))
            
            final_values = [row[0] for row in verify_result.fetchall()]
            logger.info(
                "auto_migration_completed",
                migration="add_missing_relation_type_values",
                final_values=final_values
            )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_missing_relation_type_values",
            error=str(e),
            error_type=type(e).__name__
        )
        return False
    finally:
        await engine.dispose()


async def main():
    """Main entry point."""
    success = await add_missing_relation_type_values()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
