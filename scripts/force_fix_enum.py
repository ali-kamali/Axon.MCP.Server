#!/usr/bin/env python3
"""
Force fix the enum case mismatch issue.

This script will forcefully fix the enum values regardless of current state.
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


async def force_fix_enum():
    """Force fix the enum values."""
    try:
        logger.info("force_fix_enum_started")
        
        async with engine.begin() as conn:
            # Step 1: Check current state
            result = await conn.execute(text("""
                SELECT e.enumlabel 
                FROM pg_enum e
                JOIN pg_type t ON e.enumtypid = t.oid
                WHERE t.typname = 'sourcecontrolproviderenum'
                ORDER BY e.enumsortorder;
            """))
            enum_values = [row[0] for row in result.fetchall()]
            logger.info("current_enum_values", values=enum_values)
            
            # Step 2: Check if repositories table has data
            result = await conn.execute(text("""
                SELECT COUNT(*) FROM repositories;
            """))
            repo_count = result.scalar()
            logger.info("repository_count", count=repo_count)
            
            # Step 3: Create new enum type with UPPERCASE values (to match Python enum member names)
            logger.info("creating_new_enum_type")
            await conn.execute(text("""
                DROP TYPE IF EXISTS sourcecontrolproviderenum_uppercase CASCADE;
            """))
            
            await conn.execute(text("""
                CREATE TYPE sourcecontrolproviderenum_uppercase AS ENUM ('GITLAB', 'AZUREDEVOPS');
            """))
            
            # Step 4: Add temporary column
            logger.info("adding_temporary_column")
            await conn.execute(text("""
                ALTER TABLE repositories 
                DROP COLUMN IF EXISTS provider_uppercase;
            """))
            
            await conn.execute(text("""
                ALTER TABLE repositories 
                ADD COLUMN provider_uppercase sourcecontrolproviderenum_uppercase;
            """))
            
            # Step 5: Migrate data with case conversion to UPPERCASE
            logger.info("migrating_data")
            await conn.execute(text("""
                UPDATE repositories 
                SET provider_uppercase = CASE 
                    WHEN LOWER(provider::text) = 'gitlab' THEN 'GITLAB'::sourcecontrolproviderenum_uppercase
                    WHEN LOWER(provider::text) = 'azuredevops' THEN 'AZUREDEVOPS'::sourcecontrolproviderenum_uppercase
                    ELSE 'GITLAB'::sourcecontrolproviderenum_uppercase
                END;
            """))
            
            # Step 6: Drop old column
            logger.info("dropping_old_column")
            await conn.execute(text("""
                ALTER TABLE repositories DROP COLUMN provider;
            """))
            
            # Step 7: Rename new column
            logger.info("renaming_column")
            await conn.execute(text("""
                ALTER TABLE repositories RENAME COLUMN provider_uppercase TO provider;
            """))
            
            # Step 8: Set NOT NULL and default
            logger.info("setting_constraints")
            await conn.execute(text("""
                ALTER TABLE repositories 
                ALTER COLUMN provider SET NOT NULL;
            """))
            
            await conn.execute(text("""
                ALTER TABLE repositories 
                ALTER COLUMN provider SET DEFAULT 'GITLAB'::sourcecontrolproviderenum_uppercase;
            """))
            
            # Step 9: Drop old enum type
            logger.info("dropping_old_enum_type")
            await conn.execute(text("""
                DROP TYPE IF EXISTS sourcecontrolproviderenum CASCADE;
            """))
            
            # Step 10: Rename new enum type
            logger.info("renaming_enum_type")
            await conn.execute(text("""
                ALTER TYPE sourcecontrolproviderenum_uppercase RENAME TO sourcecontrolproviderenum;
            """))
            
            # Step 11: Recreate indexes
            logger.info("recreating_indexes")
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_repositories_provider 
                ON repositories (provider);
            """))
            
            await conn.execute(text("""
                DROP INDEX IF EXISTS idx_repo_provider_path;
            """))
            
            await conn.execute(text("""
                CREATE INDEX idx_repo_provider_path 
                ON repositories (provider, path_with_namespace);
            """))
            
            # Step 12: Verify the fix
            result = await conn.execute(text("""
                SELECT e.enumlabel 
                FROM pg_enum e
                JOIN pg_type t ON e.enumtypid = t.oid
                WHERE t.typname = 'sourcecontrolproviderenum'
                ORDER BY e.enumsortorder;
            """))
            new_enum_values = [row[0] for row in result.fetchall()]
            logger.info("new_enum_values", values=new_enum_values)
            
            result = await conn.execute(text("""
                SELECT DISTINCT provider::text as provider_value
                FROM repositories;
            """))
            data_values = [row[0] for row in result.fetchall()]
            logger.info("data_provider_values", values=data_values)
        
        logger.info("force_fix_enum_completed")
        return True
        
    except Exception as e:
        logger.error(
            "force_fix_enum_failed",
            error=str(e),
            error_type=type(e).__name__
        )
        import traceback
        traceback.print_exc()
        return False
    finally:
        await engine.dispose()


if __name__ == "__main__":
    success = asyncio.run(force_fix_enum())
    sys.exit(0 if success else 1)

