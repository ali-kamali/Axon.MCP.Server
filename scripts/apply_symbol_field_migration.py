#!/usr/bin/env python3
"""
Apply database migration to increase symbol field sizes.

This script can be run directly to apply the migration without using Alembic.
It's useful for quick fixes in development or when Alembic is not available.

Usage:
    python scripts/apply_symbol_field_migration.py
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


async def check_current_schema():
    """Check current schema to see if migration is needed."""
    async with engine.begin() as conn:
        # Query information_schema to get current column types
        result = await conn.execute(text("""
            SELECT 
                column_name,
                character_maximum_length
            FROM information_schema.columns
            WHERE table_name = 'symbols'
            AND column_name IN ('name', 'fully_qualified_name', 'return_type')
            ORDER BY column_name;
        """))
        
        columns = {row[0]: row[1] for row in result}
        
        logger.info(
            "current_schema_check",
            name_length=columns.get('name'),
            fully_qualified_name_length=columns.get('fully_qualified_name'),
            return_type_length=columns.get('return_type')
        )
        
        return columns


async def apply_migration():
    """Apply the migration to increase field sizes."""
    logger.info("migration_started", migration="increase_symbol_field_sizes")
    
    try:
        # Check current schema
        current_schema = await check_current_schema()
        
        # Determine what needs to be migrated
        migrations_needed = []
        
        if current_schema.get('name') != 1000:
            migrations_needed.append('name')
        if current_schema.get('fully_qualified_name') != 2000:
            migrations_needed.append('fully_qualified_name')
        if current_schema.get('return_type') != 1000:
            migrations_needed.append('return_type')
        
        if not migrations_needed:
            logger.info(
                "migration_not_needed",
                message="Schema is already up to date"
            )
            return True
        
        logger.info(
            "applying_migrations",
            fields=migrations_needed
        )
        
        # Apply migrations
        async with engine.begin() as conn:
            if 'name' in migrations_needed:
                logger.info("migrating_field", field="name", old_size=current_schema.get('name'), new_size=1000)
                await conn.execute(text("""
                    ALTER TABLE symbols 
                    ALTER COLUMN name TYPE VARCHAR(1000);
                """))
            
            if 'fully_qualified_name' in migrations_needed:
                logger.info(
                    "migrating_field",
                    field="fully_qualified_name",
                    old_size=current_schema.get('fully_qualified_name'),
                    new_size=2000
                )
                await conn.execute(text("""
                    ALTER TABLE symbols 
                    ALTER COLUMN fully_qualified_name TYPE VARCHAR(2000);
                """))
            
            if 'return_type' in migrations_needed:
                logger.info(
                    "migrating_field",
                    field="return_type",
                    old_size=current_schema.get('return_type'),
                    new_size=1000
                )
                await conn.execute(text("""
                    ALTER TABLE symbols 
                    ALTER COLUMN return_type TYPE VARCHAR(1000);
                """))
        
        # Verify migration
        new_schema = await check_current_schema()
        
        success = (
            new_schema.get('name') == 1000 and
            new_schema.get('fully_qualified_name') == 2000 and
            new_schema.get('return_type') == 1000
        )
        
        if success:
            logger.info(
                "migration_completed_successfully",
                name_length=new_schema.get('name'),
                fully_qualified_name_length=new_schema.get('fully_qualified_name'),
                return_type_length=new_schema.get('return_type')
            )
        else:
            logger.error(
                "migration_verification_failed",
                expected_name=1000,
                actual_name=new_schema.get('name'),
                expected_fqn=2000,
                actual_fqn=new_schema.get('fully_qualified_name'),
                expected_return_type=1000,
                actual_return_type=new_schema.get('return_type')
            )
        
        return success
        
    except Exception as e:
        logger.error(
            "migration_failed",
            error=str(e),
            error_type=type(e).__name__
        )
        raise
    finally:
        await engine.dispose()


async def main():
    """Main entry point."""
    print("=" * 80)
    print("Symbol Field Size Migration")
    print("=" * 80)
    print()
    print("This script will increase the VARCHAR field sizes in the symbols table:")
    print("  - name: VARCHAR(500) -> VARCHAR(1000)")
    print("  - fully_qualified_name: VARCHAR(1000) -> VARCHAR(2000)")
    print("  - return_type: VARCHAR(255) -> VARCHAR(1000)")
    print()
    print("This migration is safe and will not cause data loss.")
    print()
    
    try:
        success = await apply_migration()
        
        if success:
            print()
            print("✓ Migration completed successfully!")
            print()
            print("Next steps:")
            print("  1. Restart Celery workers: docker-compose restart celery-worker")
            print("  2. Retry failed repository sync tasks")
            print()
            return 0
        else:
            print()
            print("✗ Migration verification failed!")
            print("Please check the logs for details.")
            print()
            return 1
            
    except Exception as e:
        print()
        print(f"✗ Migration failed with error: {e}")
        print("Please check the logs for details.")
        print()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

