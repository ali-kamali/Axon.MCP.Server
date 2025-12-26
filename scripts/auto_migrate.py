#!/usr/bin/env python3
"""
Auto-migration script that runs on application startup.

This script checks if migrations are needed and applies them automatically.
It's designed to be safe and idempotent - can be run multiple times without issues.

Usage:
    python scripts/auto_migrate.py
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


async def check_table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = :table_name
            );
        """), {"table_name": table_name})
        exists = result.scalar()
        return exists


async def get_column_info(table_name: str, column_name: str) -> dict:
    """Get column information from the database."""
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT 
                data_type,
                character_maximum_length,
                is_nullable
            FROM information_schema.columns
            WHERE table_name = :table_name
            AND column_name = :column_name;
        """), {"table_name": table_name, "column_name": column_name})
        
        row = result.fetchone()
        if not row:
            return None
        
        return {
            "data_type": row[0],
            "max_length": row[1],
            "is_nullable": row[2]
        }


async def get_indexes(table_name: str) -> list:
    """Get list of indexes for a table."""
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = :table_name;
        """), {"table_name": table_name})
        
        indexes = []
        for row in result.fetchall():
            indexes.append({
                "name": row[0],
                "definition": row[1]
            })
        
        return indexes


async def migrate_symbol_field_sizes() -> bool:
    """
    Migrate symbol table field sizes if needed.
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if symbols table exists
        if not await check_table_exists("symbols"):
            logger.info(
                "migration_skipped",
                reason="symbols table does not exist yet",
                migration="increase_symbol_field_sizes"
            )
            return True
        
        # Check current field sizes
        varchar_migrations_needed = []
        text_migrations_needed = []
        
        name_info = await get_column_info("symbols", "name")
        if name_info and name_info["max_length"] != 1000:
            varchar_migrations_needed.append(("name", name_info["max_length"], 1000))
        
        fqn_info = await get_column_info("symbols", "fully_qualified_name")
        if fqn_info and fqn_info["max_length"] != 2000:
            varchar_migrations_needed.append(("fully_qualified_name", fqn_info["max_length"], 2000))
        
        return_type_info = await get_column_info("symbols", "return_type")
        if return_type_info and return_type_info["max_length"] != 1000:
            varchar_migrations_needed.append(("return_type", return_type_info["max_length"], 1000))
        
        # Check signature field - should be TEXT, not VARCHAR
        signature_info = await get_column_info("symbols", "signature")
        if signature_info and signature_info["data_type"] != "text":
            # If it's VARCHAR (character varying), convert to TEXT
            if signature_info["data_type"] in ("character varying", "varchar"):
                text_migrations_needed.append("signature")
        
        if not varchar_migrations_needed and not text_migrations_needed:
            logger.info(
                "migration_not_needed",
                migration="increase_symbol_field_sizes",
                message="Schema is already up to date"
            )
            return True
        
        # Apply migrations
        all_fields = [m[0] for m in varchar_migrations_needed] + text_migrations_needed
        logger.info(
            "auto_migration_started",
            migration="increase_symbol_field_sizes",
            fields=all_fields
        )
        
        async with engine.begin() as conn:
            # Apply VARCHAR size increases
            for field_name, old_size, new_size in varchar_migrations_needed:
                logger.info(
                    "migrating_field",
                    field=field_name,
                    old_size=old_size,
                    new_size=new_size
                )
                
                await conn.execute(text(f"""
                    ALTER TABLE symbols 
                    ALTER COLUMN {field_name} TYPE VARCHAR({new_size});
                """))
            
            # Apply VARCHAR to TEXT conversions
            for field_name in text_migrations_needed:
                logger.info(
                    "migrating_field_to_text",
                    field=field_name,
                    old_type="VARCHAR",
                    new_type="TEXT"
                )
                
                await conn.execute(text(f"""
                    ALTER TABLE symbols 
                    ALTER COLUMN {field_name} TYPE TEXT;
                """))
        
        all_fields = [m[0] for m in varchar_migrations_needed] + text_migrations_needed
        logger.info(
            "auto_migration_completed",
            migration="increase_symbol_field_sizes",
            fields=all_fields
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="increase_symbol_field_sizes",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def migrate_azuredevops_support() -> bool:
    """
    Migrate repositories table to support Azure DevOps.
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if repositories table exists
        if not await check_table_exists("repositories"):
            logger.info(
                "migration_skipped",
                reason="repositories table does not exist yet",
                migration="add_azuredevops_support"
            )
            return True
        
        # Check if provider column already exists
        provider_info = await get_column_info("repositories", "provider")
        if provider_info:
            logger.info(
                "migration_not_needed",
                migration="add_azuredevops_support",
                message="Provider column already exists"
            )
            return True
        
        logger.info(
            "auto_migration_started",
            migration="add_azuredevops_support"
        )
        
        # Step 1: Handle enum type creation/update in a separate transaction
        # PostgreSQL requires enum values to be committed before use
        async with engine.begin() as conn:
            # Check if the enum type exists and what values it has
            enum_check = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_type WHERE typname = 'sourcecontrolproviderenum'
                );
            """))
            enum_exists = enum_check.scalar()
            
            if enum_exists:
                # Enum exists, check if it has the values we need
                enum_values = await conn.execute(text("""
                    SELECT e.enumlabel 
                    FROM pg_enum e
                    JOIN pg_type t ON e.enumtypid = t.oid
                    WHERE t.typname = 'sourcecontrolproviderenum'
                    ORDER BY e.enumsortorder;
                """))
                existing_values = [row[0] for row in enum_values.fetchall()]
                
                # Add missing enum values (uppercase)
                for value in ['GITLAB', 'AZUREDEVOPS']:
                    if value not in existing_values:
                        logger.info(
                            "adding_enum_value",
                            enum_type="sourcecontrolproviderenum",
                            value=value
                        )
                        await conn.execute(text(f"""
                            ALTER TYPE sourcecontrolproviderenum ADD VALUE IF NOT EXISTS '{value}';
                        """))
            else:
                # Create the enum type (uppercase)
                logger.info(
                    "creating_enum_type",
                    enum_type="sourcecontrolproviderenum"
                )
                await conn.execute(text("""
                    CREATE TYPE sourcecontrolproviderenum AS ENUM ('GITLAB', 'AZUREDEVOPS');
                """))
        
        # Step 2: Add columns in a new transaction (after enum values are committed)
        async with engine.begin() as conn:
            # Add provider column with default 'GITLAB' (uppercase)
            await conn.execute(text("""
                ALTER TABLE repositories 
                ADD COLUMN provider sourcecontrolproviderenum NOT NULL DEFAULT 'GITLAB';
            """))
            
            # Add Azure DevOps specific fields
            await conn.execute(text("""
                ALTER TABLE repositories 
                ADD COLUMN azuredevops_project_name VARCHAR(255),
                ADD COLUMN azuredevops_repo_id VARCHAR(255);
            """))
            
            # Add clone_url field
            await conn.execute(text("""
                ALTER TABLE repositories 
                ADD COLUMN clone_url VARCHAR(500);
            """))
            
            # Update existing repositories to populate clone_url from url field
            await conn.execute(text("""
                UPDATE repositories SET clone_url = url WHERE clone_url IS NULL;
            """))
            
            # Make clone_url non-nullable
            await conn.execute(text("""
                ALTER TABLE repositories 
                ALTER COLUMN clone_url SET NOT NULL;
            """))
            
            # Make gitlab_project_id nullable
            await conn.execute(text("""
                ALTER TABLE repositories 
                ALTER COLUMN gitlab_project_id DROP NOT NULL;
            """))
            
            # Drop unique constraint on gitlab_project_id if it exists
            await conn.execute(text("""
                DO $$ BEGIN
                    ALTER TABLE repositories DROP CONSTRAINT IF EXISTS repositories_gitlab_project_id_key;
                EXCEPTION
                    WHEN undefined_object THEN null;
                END $$;
            """))
            
            # Create new indexes
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_repo_provider_path 
                ON repositories (provider, path_with_namespace);
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_repo_gitlab_project 
                ON repositories (gitlab_project_id);
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_repo_azuredevops_project_repo 
                ON repositories (azuredevops_project_name, azuredevops_repo_id);
            """))
            
            # Update the status index
            await conn.execute(text("""
                DROP INDEX IF EXISTS idx_repo_status_updated;
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_repo_provider_status_updated 
                ON repositories (provider, status, updated_at);
            """))
        
        logger.info(
            "auto_migration_completed",
            migration="add_azuredevops_support"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_azuredevops_support",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def migrate_enhanced_features() -> bool:
    """
    Migrate database to add enhanced features (003_add_enhanced_features).
    
    Adds:
    - Structured docs, attributes, parent_name, complexity_score to symbols
    - chunk_subtype, parent_chunk_id, context_metadata to chunks
    - documents, configuration_entries, dependencies, project_references tables
    - New symbol kinds (document_section, code_example)
    - Markdown language support
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if repositories table exists (base requirement)
        if not await check_table_exists("repositories"):
            logger.info(
                "migration_skipped",
                reason="repositories table does not exist yet",
                migration="add_enhanced_features"
            )
            return True
        
        # Check if documents table already exists (indicates migration already applied)
        if await check_table_exists("documents"):
            logger.info(
                "migration_not_needed",
                migration="add_enhanced_features",
                message="Enhanced features already exist"
            )
            return True
        
        logger.info(
            "auto_migration_started",
            migration="add_enhanced_features"
        )
        
        async with engine.begin() as conn:
            # Check if structured_docs column exists (atomic check within transaction)
            structured_docs_check = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'symbols' AND column_name = 'structured_docs'
                );
            """))
            structured_docs_exists = structured_docs_check.scalar()
            
            # Add new columns to symbols table
            if not structured_docs_exists:
                await conn.execute(text("""
                    ALTER TABLE symbols 
                    ADD COLUMN structured_docs JSONB,
                    ADD COLUMN attributes JSONB,
                    ADD COLUMN parent_name VARCHAR(2000),
                    ADD COLUMN complexity_score INTEGER;
                """))
            
            # Check if chunk_subtype column exists (atomic check within transaction)
            chunk_subtype_check = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'chunks' AND column_name = 'chunk_subtype'
                );
            """))
            chunk_subtype_exists = chunk_subtype_check.scalar()
            
            # Add new columns to chunks table
            if not chunk_subtype_exists:
                await conn.execute(text("""
                    ALTER TABLE chunks 
                    ADD COLUMN chunk_subtype VARCHAR(50),
                    ADD COLUMN parent_chunk_id INTEGER,
                    ADD COLUMN context_metadata JSONB;
                """))
                
                # Add foreign key for parent_chunk_id
                await conn.execute(text("""
                    ALTER TABLE chunks 
                    ADD CONSTRAINT fk_chunks_parent_chunk 
                    FOREIGN KEY (parent_chunk_id) REFERENCES chunks(id) ON DELETE SET NULL;
                """))
                
                # Create index on parent_chunk_id
                await conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_chunks_parent_chunk_id 
                    ON chunks (parent_chunk_id);
                """))
            
            # Create documents table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS documents (
                    id SERIAL PRIMARY KEY,
                    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                    file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
                    path VARCHAR(1000) NOT NULL,
                    doc_type VARCHAR(50),
                    title VARCHAR(500),
                    content TEXT,
                    sections JSONB,
                    code_examples JSONB,
                    metadata JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_document_repo_type 
                ON documents (repository_id, doc_type);
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_document_path 
                ON documents (path);
            """))
            
            # Create configuration_entries table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS configuration_entries (
                    id SERIAL PRIMARY KEY,
                    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                    file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
                    config_key VARCHAR(500) NOT NULL,
                    config_value TEXT,
                    config_type VARCHAR(50),
                    environment VARCHAR(50),
                    is_secret INTEGER NOT NULL DEFAULT 0,
                    file_path VARCHAR(1000),
                    line_number INTEGER,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_config_key 
                ON configuration_entries (config_key);
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_config_repo_env 
                ON configuration_entries (repository_id, environment);
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_config_secret 
                ON configuration_entries (is_secret);
            """))
            
            # Create dependencies table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS dependencies (
                    id SERIAL PRIMARY KEY,
                    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                    file_id INTEGER REFERENCES files(id) ON DELETE CASCADE,
                    package_name VARCHAR(255) NOT NULL,
                    package_version VARCHAR(100),
                    dependency_type VARCHAR(50),
                    is_dev_dependency INTEGER NOT NULL DEFAULT 0,
                    file_path VARCHAR(1000),
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_dep_package 
                ON dependencies (package_name);
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_dep_repo_type 
                ON dependencies (repository_id, dependency_type);
            """))
            
            # Create project_references table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS project_references (
                    id SERIAL PRIMARY KEY,
                    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                    source_project_path VARCHAR(1000) NOT NULL,
                    target_project_path VARCHAR(1000) NOT NULL,
                    reference_type VARCHAR(50),
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_proj_ref_repo 
                ON project_references (repository_id);
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_proj_ref_source 
                ON project_references (source_project_path);
            """))
            
            # Update LanguageEnum to include markdown (uppercase)
            # Check if MARKDOWN is already in the enum
            enum_check = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_enum e
                    JOIN pg_type t ON e.enumtypid = t.oid
                    WHERE t.typname = 'languageenum' 
                    AND e.enumlabel = 'MARKDOWN'
                );
            """))
            has_markdown = enum_check.scalar()
            
            if not has_markdown:
                # Add MARKDOWN to language enum
                # Note: PostgreSQL doesn't support IF NOT EXISTS for ALTER TYPE ADD VALUE
                # We check first to avoid errors
                try:
                    await conn.execute(text("""
                        ALTER TYPE languageenum ADD VALUE 'MARKDOWN';
                    """))
                except Exception as enum_error:
                    # If it already exists, that's fine
                    if 'already exists' not in str(enum_error).lower():
                        raise
        
        logger.info(
            "auto_migration_completed",
            migration="add_enhanced_features"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_enhanced_features",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def migrate_symbol_enhancements() -> bool:
    """
    Migrate database to add symbol enhancements (004_add_symbol_enhancements).
    
    Adds:
    - is_test, is_generated, usage_count to symbols
    - last_modified_by, git_blame_commit to symbols
    - SQL language support
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if symbols table exists
        if not await check_table_exists("symbols"):
            logger.info(
                "migration_skipped",
                reason="symbols table does not exist yet",
                migration="add_symbol_enhancements"
            )
            return True
        
        # Check if is_test column already exists (indicates migration already applied)
        is_test_info = await get_column_info("symbols", "is_test")
        if is_test_info:
            logger.info(
                "migration_not_needed",
                migration="add_symbol_enhancements",
                message="Symbol enhancements already exist"
            )
            return True
        
        logger.info(
            "auto_migration_started",
            migration="add_symbol_enhancements"
        )
        
        async with engine.begin() as conn:
            # Add new columns to symbols table
            await conn.execute(text("""
                ALTER TABLE symbols 
                ADD COLUMN is_test INTEGER NOT NULL DEFAULT 0,
                ADD COLUMN is_generated INTEGER NOT NULL DEFAULT 0,
                ADD COLUMN usage_count INTEGER NOT NULL DEFAULT 0,
                ADD COLUMN last_modified_by VARCHAR(255),
                ADD COLUMN git_blame_commit VARCHAR(40);
            """))
            
            # Add indexes for new columns
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_symbol_is_test 
                ON symbols (is_test);
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_symbol_is_generated 
                ON symbols (is_generated);
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_symbol_usage_count 
                ON symbols (usage_count);
            """))
            
            # Update LanguageEnum to include SQL (uppercase)
            # Check if SQL is already in the enum
            enum_check = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_enum e
                    JOIN pg_type t ON e.enumtypid = t.oid
                    WHERE t.typname = 'languageenum' 
                    AND e.enumlabel = 'SQL'
                );
            """))
            has_sql = enum_check.scalar()
            
            if not has_sql:
                # Add SQL to language enum
                # Note: PostgreSQL doesn't support IF NOT EXISTS for ALTER TYPE ADD VALUE
                # We check first to avoid errors
                try:
                    await conn.execute(text("""
                        ALTER TYPE languageenum ADD VALUE 'SQL';
                    """))
                except Exception as enum_error:
                    # If it already exists, that's fine
                    if 'already exists' not in str(enum_error).lower():
                        raise
        
        logger.info(
            "auto_migration_completed",
            migration="add_symbol_enhancements"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_symbol_enhancements",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def fix_enum_case_mismatch() -> bool:
    """
    Fix case mismatch in enum values.
    
    The database enum may have uppercase values (GITLAB, AZUREDEVOPS) while
    Python expects lowercase (gitlab, azuredevops). This migration fixes that.
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if repositories table exists
        if not await check_table_exists("repositories"):
            logger.info(
                "migration_skipped",
                reason="repositories table does not exist yet",
                migration="fix_enum_case_mismatch"
            )
            return True
        
        # Check if provider column exists
        provider_info = await get_column_info("repositories", "provider")
        if not provider_info:
            logger.info(
                "migration_skipped",
                reason="provider column does not exist yet",
                migration="fix_enum_case_mismatch"
            )
            return True
        
        async with engine.begin() as conn:
            # Check current enum values
            enum_values_result = await conn.execute(text("""
                SELECT e.enumlabel 
                FROM pg_enum e
                JOIN pg_type t ON e.enumtypid = t.oid
                WHERE t.typname = 'sourcecontrolproviderenum'
                ORDER BY e.enumsortorder;
            """))
            existing_values = [row[0] for row in enum_values_result.fetchall()]
            
            if not existing_values:
                logger.info(
                    "migration_skipped",
                    reason="enum type does not exist or has no values",
                    migration="fix_enum_case_mismatch"
                )
                return True
            
            # Check if we have uppercase values (which are correct)
            has_uppercase = 'GITLAB' in existing_values or 'AZUREDEVOPS' in existing_values
            has_lowercase = 'gitlab' in existing_values or 'azuredevops' in existing_values
            
            # If we already have uppercase values and no lowercase, we're good
            if has_uppercase and not has_lowercase:
                logger.info(
                    "migration_not_needed",
                    migration="fix_enum_case_mismatch",
                    message="Enum values are already uppercase (correct)"
                )
                return True
            
            # If no values found at all, skip
            if not has_lowercase and not has_uppercase:
                logger.info(
                    "migration_not_needed",
                    migration="fix_enum_case_mismatch",
                    message="No enum values found"
                )
                return True
            
            logger.info(
                "auto_migration_started",
                migration="fix_enum_case_mismatch",
                existing_values=existing_values,
                needs_fix=has_uppercase
            )
            
            # Strategy: Create new enum with uppercase values, migrate data, switch column type
            
            # Step 1: Create new enum type with uppercase values
            await conn.execute(text("""
                DROP TYPE IF EXISTS sourcecontrolproviderenum_new CASCADE;
            """))
            await conn.execute(text("""
                CREATE TYPE sourcecontrolproviderenum_new AS ENUM ('GITLAB', 'AZUREDEVOPS');
            """))
            
            # Step 2: Check if repositories table has data
            repo_count_result = await conn.execute(text("SELECT COUNT(*) FROM repositories"))
            repo_count = repo_count_result.scalar() or 0
            
            if repo_count > 0:
                # Step 3: Add temporary column with new enum type
                await conn.execute(text("""
                    ALTER TABLE repositories 
                    ADD COLUMN provider_new sourcecontrolproviderenum_new;
                """))
                
                # Step 4: Migrate data with case conversion to uppercase
                await conn.execute(text("""
                    UPDATE repositories 
                    SET provider_new = CASE 
                        WHEN UPPER(provider::text) = 'GITLAB' THEN 'GITLAB'::sourcecontrolproviderenum_new
                        WHEN UPPER(provider::text) = 'AZUREDEVOPS' THEN 'AZUREDEVOPS'::sourcecontrolproviderenum_new
                        ELSE 'GITLAB'::sourcecontrolproviderenum_new
                    END;
                """))
                
                # Step 5: Drop old column
                await conn.execute(text("""
                    ALTER TABLE repositories DROP COLUMN provider;
                """))
                
                # Step 6: Rename temp column to provider
                await conn.execute(text("""
                    ALTER TABLE repositories RENAME COLUMN provider_new TO provider;
                """))
                # Step 7: Make the column NOT NULL
                await conn.execute(text("""
                    ALTER TABLE repositories ALTER COLUMN provider SET NOT NULL;
                """))
                
                # Step 8: Recreate indexes
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
            
            # Step 9: Drop old enum type (no CASCADE needed since column is already dropped)
            await conn.execute(text("""
                DROP TYPE IF EXISTS sourcecontrolproviderenum;
            """))
            
            # Step 10: Rename new enum type to original name
            await conn.execute(text("""
                ALTER TYPE sourcecontrolproviderenum_new RENAME TO sourcecontrolproviderenum;
            """))
            
            # Step 11: Set default value (after renaming the type)
            if repo_count > 0:
                await conn.execute(text("""
                    ALTER TABLE repositories 
                    ALTER COLUMN provider SET DEFAULT 'GITLAB'::sourcecontrolproviderenum;
                """))
            
            logger.info(
                "auto_migration_completed",
                migration="fix_enum_case_mismatch"
            )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="fix_enum_case_mismatch",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def migrate_rename_document_metadata() -> bool:
    """
    Rename documents.metadata to documents.doc_metadata.
    
    This fixes the SQLAlchemy reserved attribute name conflict.
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if documents table exists
        if not await check_table_exists("documents"):
            logger.info(
                "migration_skipped",
                reason="documents table does not exist yet",
                migration="rename_document_metadata_column"
            )
            return True
        
        # Check if doc_metadata column already exists (indicates migration already applied)
        doc_metadata_info = await get_column_info("documents", "doc_metadata")
        if doc_metadata_info:
            logger.info(
                "migration_not_needed",
                migration="rename_document_metadata_column",
                message="doc_metadata column already exists"
            )
            return True
        
        # Check if old metadata column exists
        metadata_info = await get_column_info("documents", "metadata")
        if not metadata_info:
            logger.info(
                "migration_not_needed",
                migration="rename_document_metadata_column",
                message="metadata column does not exist"
            )
            return True
        
        logger.info(
            "auto_migration_started",
            migration="rename_document_metadata_column"
        )
        
        async with engine.begin() as conn:
            # Rename the column
            await conn.execute(text("""
                ALTER TABLE documents 
                RENAME COLUMN metadata TO doc_metadata;
            """))
        
        logger.info(
            "auto_migration_completed",
            migration="rename_document_metadata_column"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="rename_document_metadata_column",
            error=str(e),
            error_type=type(e).__name__
        )
        return False



async def migrate_add_endpoint_to_symbolkind() -> bool:
    """
    Add ENDPOINT to symbolkindenum.
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if symbols table exists
        if not await check_table_exists("symbols"):
            logger.info(
                "migration_skipped",
                reason="symbols table does not exist yet",
                migration="add_endpoint_to_symbolkind"
            )
            return True
            
        logger.info(
            "auto_migration_started",
            migration="add_endpoint_to_symbolkind"
        )
        
        async with engine.begin() as conn:
            # Check if ENDPOINT is already in the enum
            enum_check = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_enum e
                    JOIN pg_type t ON e.enumtypid = t.oid
                    WHERE t.typname = 'symbolkindenum' 
                    AND e.enumlabel = 'ENDPOINT'
                );
            """))
            has_endpoint = enum_check.scalar()
            
            if not has_endpoint:
                # Add ENDPOINT to symbolkindenum
                try:
                    await conn.execute(text("""
                        ALTER TYPE symbolkindenum ADD VALUE 'ENDPOINT';
                    """))
                    logger.info(
                        "added_enum_value",
                        enum_type="symbolkindenum",
                        value="ENDPOINT"
                    )
                except Exception as enum_error:
                    # If it already exists (race condition), that's fine
                    if 'already exists' not in str(enum_error).lower():
                        raise
            else:
                logger.info(
                    "migration_not_needed",
                    migration="add_endpoint_to_symbolkind",
                    message="ENDPOINT already exists in symbolkindenum"
                )
        
        logger.info(
            "auto_migration_completed",
            migration="add_endpoint_to_symbolkind"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_endpoint_to_symbolkind",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def migrate_add_missing_relation_types() -> bool:
    """
    Add OVERRIDES and REFERENCES to relationtypeenum if they don't exist.
    
    This is a dedicated migration to ensure these specific enum values are present.
    It's simpler and more targeted than the general verify_enum_values migration.
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        logger.info(
            "auto_migration_started",
            migration="add_missing_relation_types"
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
                    migration="add_missing_relation_types"
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
                migration="add_missing_relation_types",
                values=existing_values
            )
            
            # Values we need to add
            required_values = ['OVERRIDES', 'REFERENCES']
            missing_values = [v for v in required_values if v not in existing_values]
            
            if not missing_values:
                logger.info(
                    "migration_not_needed",
                    migration="add_missing_relation_types",
                    message="All required values already exist"
                )
                return True
            
            logger.info(
                "adding_missing_values",
                migration="add_missing_relation_types",
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
                migration="add_missing_relation_types",
                final_values=final_values
            )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_missing_relation_types",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def verify_enum_values() -> bool:

    """
    Verify enum values are correct (006_verify_enum_values).
    
    This migration verifies that:
    - All enum types use uppercase values consistently
    - All enum values are uppercase
    - Data integrity is maintained
    
    Returns:
        True if verification passed or was not needed, False on error
    """
    try:
        # Check if symbols table exists (indicates database is initialized)
        if not await check_table_exists("symbols"):
            logger.info(
                "migration_skipped",
                reason="symbols table does not exist yet",
                migration="verify_enum_values"
            )
            return True
        
        logger.info(
            "auto_migration_started",
            migration="verify_enum_values"
        )
        
        async with engine.begin() as conn:
            # Define expected uppercase enum values
            enum_definitions = {
                'languageenum': ['CSHARP', 'JAVASCRIPT', 'TYPESCRIPT', 'VUE', 'PYTHON', 'GO', 'JAVA', 'MARKDOWN', 'SQL', 'UNKNOWN'],
                'sourcecontrolproviderenum': ['GITLAB', 'AZUREDEVOPS'],
                'symbolkindenum': ['FUNCTION', 'METHOD', 'CLASS', 'INTERFACE', 'STRUCT', 'ENUM', 'VARIABLE', 'CONSTANT', 'PROPERTY', 'NAMESPACE', 'MODULE', 'TYPE_ALIAS', 'DOCUMENT_SECTION', 'CODE_EXAMPLE', 'ENDPOINT'],
                'accessmodifierenum': ['PUBLIC', 'PRIVATE', 'PROTECTED', 'INTERNAL', 'PROTECTED_INTERNAL', 'PRIVATE_PROTECTED'],
                'relationtypeenum': ['CALLS', 'IMPORTS', 'EXPORTS', 'INHERITS', 'IMPLEMENTS', 'USES', 'CONTAINS', 'OVERRIDES', 'REFERENCES'],
                'repositorystatusenum': ['PENDING', 'CLONING', 'PARSING', 'EXTRACTING', 'EMBEDDING', 'COMPLETED', 'FAILED'],
                'jobstatusenum': ['PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', 'RETRYING'],
                'workerstatusenum': ['ONLINE', 'OFFLINE', 'BUSY', 'STARTING', 'UNKNOWN']
            }
            
            # Mapping of enum types to their table/column usage for data migration
            enum_usage = {
                'languageenum': [
                    ('files', 'language'),
                    ('symbols', 'language')
                ],
                'sourcecontrolproviderenum': [
                    ('repositories', 'provider')
                ],
                'symbolkindenum': [
                    ('symbols', 'kind')
                ],
                'accessmodifierenum': [
                    ('symbols', 'access_modifier')
                ],
                'relationtypeenum': [
                    ('relations', 'relation_type')
                ],
                'repositorystatusenum': [
                    ('repositories', 'status')
                ],
                'jobstatusenum': [
                    ('jobs', 'status')
                ],
                'workerstatusenum': [
                    ('workers', 'status')
                ]
            }
            
            # Verify and convert each enum type
            for enum_type, expected_values in enum_definitions.items():
                try:
                    # Check if enum type exists
                    type_check = await conn.execute(text("""
                        SELECT EXISTS (
                            SELECT 1 FROM pg_type WHERE typname = :enum_type
                        )
                    """), {"enum_type": enum_type})
                    
                    if not type_check.scalar():
                        logger.debug(
                            "enum_type_not_found",
                            migration="verify_enum_values",
                            enum_type=enum_type
                        )
                        continue
                    
                    # Get current enum values
                    enum_check = await conn.execute(text("""
                        SELECT enumlabel 
                        FROM pg_enum 
                        WHERE enumtypid = (
                            SELECT oid 
                            FROM pg_type 
                            WHERE typname = :enum_type
                        )
                        ORDER BY enumsortorder
                    """), {"enum_type": enum_type})
                    
                    enum_values = [row[0] for row in enum_check]
                    
                    # Check if all values are uppercase
                    all_uppercase = all(v == v.upper() for v in enum_values)
                    needs_conversion = any(v != v.upper() for v in enum_values)
                    
                    if all_uppercase:
                        logger.info(
                            "enum_verification_passed",
                            migration="verify_enum_values",
                            enum_type=enum_type,
                            values=enum_values
                        )
                        continue
                    
                    # Convert lowercase values to uppercase
                    logger.info(
                        "enum_conversion_started",
                        migration="verify_enum_values",
                        enum_type=enum_type,
                        current_values=enum_values
                    )
                    
                    # Create mapping from current values to uppercase
                    value_mapping = {}
                    for current_val in enum_values:
                        upper_val = current_val.upper()
                        # Handle special cases like type_alias -> TYPE_ALIAS
                        if upper_val not in expected_values:
                            # Try to find matching value in expected (handles underscores)
                            for exp_val in expected_values:
                                if exp_val.replace('_', '').upper() == upper_val.replace('_', ''):
                                    value_mapping[current_val] = exp_val
                                    break
                            else:
                                value_mapping[current_val] = upper_val
                        else:
                            value_mapping[current_val] = upper_val
                    
                    logger.info(
                        "enum_value_mapping",
                        migration="verify_enum_values",
                        enum_type=enum_type,
                        mapping=value_mapping
                    )
                    
                    # Create new enum type with uppercase values
                    new_enum_name = f"{enum_type}_new"
                    # Escape single quotes in enum values
                    escaped_values = [v.replace("'", "''") for v in expected_values]
                    uppercase_values_str = "', '".join(escaped_values)
                    
                    await conn.execute(text(f"""
                        DROP TYPE IF EXISTS {new_enum_name} CASCADE
                    """))
                    
                    await conn.execute(text(f"""
                        CREATE TYPE {new_enum_name} AS ENUM ('{uppercase_values_str}')
                    """))
                    
                    # Migrate data if tables exist
                    if enum_type in enum_usage:
                        for table_name, column_name in enum_usage[enum_type]:
                            try:
                                # Check if table exists
                                table_check = await conn.execute(text(f"""
                                    SELECT EXISTS (
                                        SELECT 1 FROM information_schema.tables 
                                        WHERE table_name = '{table_name}'
                                    )
                                """))
                                
                                if not table_check.scalar():
                                    logger.debug(
                                        "table_not_found",
                                        migration="verify_enum_values",
                                        table=table_name
                                    )
                                    continue
                                
                                # Check if column exists
                                col_check = await conn.execute(text(f"""
                                    SELECT EXISTS (
                                        SELECT 1 FROM information_schema.columns 
                                        WHERE table_name = '{table_name}' 
                                        AND column_name = '{column_name}'
                                    )
                                """))
                                
                                if not col_check.scalar():
                                    logger.debug(
                                        "column_not_found",
                                        migration="verify_enum_values",
                                        table=table_name,
                                        column=column_name
                                    )
                                    continue
                                
                                # Check if table has data
                                count_result = await conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                                row_count = count_result.scalar() or 0
                                
                                if row_count > 0:
                                    logger.info(
                                        "enum_data_migration_started",
                                        migration="verify_enum_values",
                                        enum_type=enum_type,
                                        table=table_name,
                                        column=column_name,
                                        row_count=row_count
                                    )
                                    
                                    # Add temporary column
                                    temp_col = f"{column_name}_new"
                                    await conn.execute(text(f"""
                                        ALTER TABLE {table_name} 
                                        ADD COLUMN {temp_col} {new_enum_name}
                                    """))
                                    
                                    # Build CASE statement for migration
                                    case_parts = []
                                    for old_val, new_val in value_mapping.items():
                                        # Escape single quotes in values
                                        old_val_escaped = old_val.replace("'", "''")
                                        new_val_escaped = new_val.replace("'", "''")
                                        case_parts.append(f"WHEN LOWER({column_name}::text) = '{old_val_escaped.lower()}' THEN '{new_val_escaped}'::{new_enum_name}")
                                    
                                    # Default to first expected value if no match
                                    default_val = expected_values[0].replace("'", "''")
                                    case_statement = "CASE\n" + "\n".join(case_parts) + f"\nELSE '{default_val}'::{new_enum_name}\nEND"
                                    
                                    # Migrate data
                                    await conn.execute(text(f"""
                                        UPDATE {table_name} 
                                        SET {temp_col} = {case_statement}
                                    """))
                                    
                                    # Drop old column
                                    await conn.execute(text(f"""
                                        ALTER TABLE {table_name} DROP COLUMN {column_name}
                                    """))
                                    
                                    # Rename new column
                                    await conn.execute(text(f"""
                                        ALTER TABLE {table_name} RENAME COLUMN {temp_col} TO {column_name}
                                    """))
                                    
                                    # Restore NOT NULL if it was set
                                    # Most enum columns should be NOT NULL
                                    try:
                                        await conn.execute(text(f"""
                                            ALTER TABLE {table_name} ALTER COLUMN {column_name} SET NOT NULL
                                        """))
                                    except Exception:
                                        pass  # Column might be nullable, that's okay
                                    
                                    logger.info(
                                        "enum_data_migration_completed",
                                        migration="verify_enum_values",
                                        table=table_name,
                                        column=column_name
                                    )
                                else:
                                    logger.debug(
                                        "table_empty",
                                        migration="verify_enum_values",
                                        table=table_name
                                    )
                                    
                            except Exception as e:
                                logger.warning(
                                    "enum_data_migration_error",
                                    migration="verify_enum_values",
                                    table=table_name,
                                    column=column_name,
                                    error=str(e)
                                )
                                # Continue with other tables
                    
                    # Drop old enum type
                    await conn.execute(text(f"""
                        DROP TYPE IF EXISTS {enum_type} CASCADE
                    """))
                    
                    # Rename new enum type
                    await conn.execute(text(f"""
                        ALTER TYPE {new_enum_name} RENAME TO {enum_type}
                    """))
                    
                    # Verify the conversion
                    verify_result = await conn.execute(text(f"""
                        SELECT enumlabel 
                        FROM pg_enum 
                        WHERE enumtypid = (
                            SELECT oid 
                            FROM pg_type 
                            WHERE typname = '{enum_type}'
                        )
                        ORDER BY enumsortorder
                    """))
                    
                    new_values = [row[0] for row in verify_result]
                    logger.info(
                        "enum_conversion_completed",
                        migration="verify_enum_values",
                        enum_type=enum_type,
                        new_values=new_values
                    )
                    
                except Exception as e:
                    logger.error(
                        "enum_conversion_error",
                        migration="verify_enum_values",
                        enum_type=enum_type,
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    # Continue with other enum types   
        
        logger.info(
            "auto_migration_completed",
            migration="verify_enum_values"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="verify_enum_values",
            error=str(e),
            error_type=type(e).__name__
        )
        return False



async def migrate_event_subscription_symbol_nullable() -> bool:
    """
    Make symbol_id nullable in event_subscriptions table.
    
    This allows event subscriptions to be saved even when the consumer class
    Symbol is not found in the database.
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if event_subscriptions table exists
        if not await check_table_exists("event_subscriptions"):
            logger.info(
                "migration_skipped",
                reason="event_subscriptions table does not exist yet",
                migration="make_event_subscription_symbol_nullable"
            )
            return True
        
        # Check if symbol_id is already nullable
        symbol_id_info = await get_column_info("event_subscriptions", "symbol_id")
        if not symbol_id_info:
            logger.info(
                "migration_skipped",
                reason="symbol_id column does not exist",
                migration="make_event_subscription_symbol_nullable"
            )
            return True
        
        # Check if already nullable
        if symbol_id_info["is_nullable"] == "YES":
            logger.info(
                "migration_not_needed",
                migration="make_event_subscription_symbol_nullable",
                message="symbol_id is already nullable"
            )
            return True
        
        logger.info(
            "auto_migration_started",
            migration="make_event_subscription_symbol_nullable"
        )
        
        async with engine.begin() as conn:
            # Make symbol_id nullable
            await conn.execute(text("""
                ALTER TABLE event_subscriptions 
                ALTER COLUMN symbol_id DROP NOT NULL;
            """))
        
        logger.info(
            "auto_migration_completed",
            migration="make_event_subscription_symbol_nullable"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="make_event_subscription_symbol_nullable",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def migrate_add_documentation_symbol_kinds() -> bool:
    """
    Add DOCUMENT_SECTION and CODE_EXAMPLE to SymbolKindEnum.
    
    These symbol kinds are needed for the search_documentation tool to work correctly.
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        logger.info(
            "auto_migration_started",
            migration="add_documentation_symbol_kinds"
        )
        
        async with engine.begin() as conn:
            # Check if symbolkindenum type exists
            type_check = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_type WHERE typname = 'symbolkindenum'
                );
            """))
            
            if not type_check.scalar():
                logger.info(
                    "migration_skipped",
                    reason="symbolkindenum type does not exist yet",
                    migration="add_documentation_symbol_kinds"
                )
                return True
            
            # Get current enum values
            enum_check = await conn.execute(text("""
                SELECT enumlabel 
                FROM pg_enum 
                WHERE enumtypid = (
                    SELECT oid 
                    FROM pg_type 
                    WHERE typname = 'symbolkindenum'
                )
                ORDER BY enumsortorder;
            """))
            
            existing_values = [row[0] for row in enum_check.fetchall()]
            
            # Check if DOCUMENT_SECTION and CODE_EXAMPLE already exist
            has_document_section = 'DOCUMENT_SECTION' in existing_values
            has_code_example = 'CODE_EXAMPLE' in existing_values
            
            if has_document_section and has_code_example:
                logger.info(
                    "migration_not_needed",
                    migration="add_documentation_symbol_kinds",
                    message="DOCUMENT_SECTION and CODE_EXAMPLE already exist"
                )
                return True
            
            # Add missing enum values
            values_to_add = []
            if not has_document_section:
                values_to_add.append('DOCUMENT_SECTION')
            if not has_code_example:
                values_to_add.append('CODE_EXAMPLE')
            
            logger.info(
                "adding_enum_values",
                migration="add_documentation_symbol_kinds",
                values=values_to_add
            )
            
            for value in values_to_add:
                # PostgreSQL 9.1+ supports IF NOT EXISTS, but we check first to be safe
                try:
                    await conn.execute(text(f"""
                        ALTER TYPE symbolkindenum ADD VALUE IF NOT EXISTS '{value}';
                    """))
                    logger.info(
                        "enum_value_added",
                        migration="add_documentation_symbol_kinds",
                        value=value
                    )
                except Exception as e:
                    # If it already exists, that's fine
                    if 'already exists' in str(e).lower():
                        logger.info(
                            "enum_value_already_exists",
                            migration="add_documentation_symbol_kinds",
                            value=value
                        )
                    else:
                        raise
        
        logger.info(
            "auto_migration_completed",
            migration="add_documentation_symbol_kinds"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_documentation_symbol_kinds",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def migrate_module_content_hash() -> bool:
    """
    Add content_hash column to module_summaries table.
    
    This column stores a hash of the module's content to detect changes
    and avoid unnecessary summary regeneration.
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if module_summaries table exists
        if not await check_table_exists("module_summaries"):
            logger.info(
                "migration_skipped",
                reason="module_summaries table does not exist yet",
                migration="add_module_content_hash"
            )
            return True
        
        # Check if content_hash column already exists
        content_hash_info = await get_column_info("module_summaries", "content_hash")
        if content_hash_info:
            logger.info(
                "migration_not_needed",
                migration="add_module_content_hash",
                message="content_hash column already exists"
            )
            return True
        
        logger.info(
            "auto_migration_started",
            migration="add_module_content_hash"
        )
        
        async with engine.begin() as conn:
            # Add content_hash column
            await conn.execute(text("""
                ALTER TABLE module_summaries 
                ADD COLUMN content_hash VARCHAR(64);
            """))
        
        logger.info(
            "auto_migration_completed",
            migration="add_module_content_hash"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_module_content_hash",
            error=str(e),
            error_type=type(e).__name__
        )
        return False



async def migrate_dependency_enhancements() -> bool:
    """
    Migrate database to add dependency enhancements.
    
    Adds:
    - is_transitive, license, version_constraint to dependencies table
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if dependencies table exists
        if not await check_table_exists("dependencies"):
            logger.info(
                "migration_skipped",
                reason="dependencies table does not exist yet",
                migration="add_dependency_enhancements"
            )
            return True
        
        # Check if is_transitive column already exists
        is_transitive_info = await get_column_info("dependencies", "is_transitive")
        if is_transitive_info:
            logger.info(
                "migration_not_needed",
                migration="add_dependency_enhancements",
                message="Dependency enhancements already exist"
            )
            return True
        
        logger.info(
            "auto_migration_started",
            migration="add_dependency_enhancements"
        )
        
        async with engine.begin() as conn:
            # Add new columns to dependencies table
            await conn.execute(text("""
                ALTER TABLE dependencies 
                ADD COLUMN is_transitive INTEGER NOT NULL DEFAULT 0,
                ADD COLUMN license VARCHAR(100),
                ADD COLUMN version_constraint VARCHAR(100);
            """))
        
        logger.info(
            "auto_migration_completed",
            migration="add_dependency_enhancements"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_dependency_enhancements",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def migrate_solution_parser_tables() -> bool:
    """
    Migrate database to add Solution and Project tables.
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if solutions table exists
        if await check_table_exists("solutions"):
            logger.info(
                "migration_not_needed",
                migration="add_solution_parser_tables",
                message="Solution and Project tables already exist"
            )
            return True
        
        logger.info(
            "auto_migration_started",
            migration="add_solution_parser_tables"
        )
        
        async with engine.begin() as conn:
            # Create solutions table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS solutions (
                    id SERIAL PRIMARY KEY,
                    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                    file_path VARCHAR(1000) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    format_version VARCHAR(50),
                    visual_studio_version VARCHAR(50),
                    visual_studio_full_version VARCHAR(50),
                    minimum_visual_studio_version VARCHAR(50),
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_solution_repo 
                ON solutions (repository_id);
            """))
            
            # Create projects table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS projects (
                    id SERIAL PRIMARY KEY,
                    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                    solution_id INTEGER REFERENCES solutions(id) ON DELETE SET NULL,
                    project_guid VARCHAR(36),
                    name VARCHAR(255) NOT NULL,
                    file_path VARCHAR(1000) NOT NULL,
                    project_type VARCHAR(100),
                    project_type_guid VARCHAR(36),
                    assembly_name VARCHAR(255),
                    target_framework VARCHAR(100),
                    output_type VARCHAR(50),
                    define_constants JSONB,
                    lang_version VARCHAR(20),
                    nullable_context VARCHAR(50),
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_project_repo 
                ON projects (repository_id);
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_project_solution 
                ON projects (solution_id);
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_project_guid 
                ON projects (project_guid);
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_project_name 
                ON projects (name);
            """))
        
        logger.info(
            "auto_migration_completed",
            migration="add_solution_parser_tables"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_solution_parser_tables",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def migrate_generics_support() -> bool:
    """
    Migrate symbols table to support generics (generic_parameters, constraints).
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        if not await check_table_exists("symbols"):
            logger.info(
                "migration_skipped",
                reason="symbols table does not exist yet",
                migration="add_generics_support"
            )
            return True
            
        # Check for generic_parameters column
        gp_info = await get_column_info("symbols", "generic_parameters")
        cons_info = await get_column_info("symbols", "constraints")
        
        if gp_info and cons_info:
            logger.info(
                "migration_not_needed",
                migration="add_generics_support",
                message="Generics columns already exist"
            )
            return True
            
        logger.info(
            "auto_migration_started",
            migration="add_generics_support"
        )
        
        async with engine.begin() as conn:
            if not gp_info:
                await conn.execute(text("""
                    ALTER TABLE symbols 
                    ADD COLUMN generic_parameters JSON;
                """))
                
            if not cons_info:
                await conn.execute(text("""
                    ALTER TABLE symbols 
                    ADD COLUMN constraints JSON;
                """))
                
        logger.info(
            "auto_migration_completed",
            migration="add_generics_support"
        )
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_generics_support",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def migrate_add_project_id_to_symbols() -> bool:
    """
    Add project_id column to symbols table.
    
    This links symbols to projects for better organization and querying.
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if symbols table exists
        if not await check_table_exists("symbols"):
            logger.info(
                "migration_skipped",
                reason="symbols table does not exist yet",
                migration="add_project_id_to_symbols"
            )
            return True
        
        # Check if project_id column already exists
        project_id_info = await get_column_info("symbols", "project_id")
        if project_id_info:
            logger.info(
                "migration_not_needed",
                migration="add_project_id_to_symbols",
                message="project_id column already exists"
            )
            return True
        
        logger.info(
            "auto_migration_started",
            migration="add_project_id_to_symbols"
        )
        
        # Check if projects table exists (before transaction)
        projects_exists = await check_table_exists("projects")
        
        async with engine.begin() as conn:
            if projects_exists:
                # Add project_id column with foreign key constraint
                await conn.execute(text("""
                    ALTER TABLE symbols 
                    ADD COLUMN project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL;
                """))
                
                # Add index on project_id for better query performance
                await conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_symbols_project_id 
                    ON symbols (project_id);
                """))
            else:
                # Add project_id column without foreign key if projects table doesn't exist yet
                await conn.execute(text("""
                    ALTER TABLE symbols 
                    ADD COLUMN project_id INTEGER;
                """))
                
                # Add index on project_id
                await conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_symbols_project_id 
                    ON symbols (project_id);
                """))
        
        logger.info(
            "auto_migration_completed",
            migration="add_project_id_to_symbols"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_project_id_to_symbols",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def migrate_partial_class_support() -> bool:
    """
    Add partial class support columns to symbols table.
    
    Adds:
    - is_partial: Boolean flag for partial classes/interfaces/structs
    - partial_definition_files: JSON array of file_ids where symbol is defined
    - merged_from_partial_ids: JSON array of symbol_ids that were merged
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if symbols table exists
        if not await check_table_exists("symbols"):
            logger.info(
                "migration_skipped",
                reason="symbols table does not exist yet",
                migration="add_partial_class_support"
            )
            return True
        
        # Check if is_partial column already exists
        is_partial_info = await get_column_info("symbols", "is_partial")
        if is_partial_info:
            logger.info(
                "migration_not_needed",
                migration="add_partial_class_support",
                message="Partial class support columns already exist"
            )
            return True
        
        logger.info(
            "auto_migration_started",
            migration="add_partial_class_support"
        )
        
        async with engine.begin() as conn:
            # Add partial class support columns
            await conn.execute(text("""
                ALTER TABLE symbols 
                ADD COLUMN is_partial INTEGER NOT NULL DEFAULT 0,
                ADD COLUMN partial_definition_files JSON,
                ADD COLUMN merged_from_partial_ids JSON;
            """))
            
            # Add index on is_partial for better query performance
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_symbols_is_partial 
                ON symbols (is_partial);
            """))
        
        logger.info(
            "auto_migration_completed",
            migration="add_partial_class_support"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_partial_class_support",
            error=str(e),
            error_type=type(e).__name__
        )
        return False



async def migrate_add_assembly_name_to_symbols() -> bool:
    """
    Add assembly_name column to symbols table.
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if symbols table exists
        if not await check_table_exists("symbols"):
            logger.info(
                "migration_skipped",
                reason="symbols table does not exist yet",
                migration="add_assembly_name_to_symbols"
            )
            return True
        
        # Check if assembly_name column already exists
        assembly_name_info = await get_column_info("symbols", "assembly_name")
        if assembly_name_info:
            logger.info(
                "migration_not_needed",
                migration="add_assembly_name_to_symbols",
                message="assembly_name column already exists"
            )
            return True
        
        logger.info(
            "auto_migration_started",
            migration="add_assembly_name_to_symbols"
        )
        
        async with engine.begin() as conn:
            # Add assembly_name column
            await conn.execute(text("""
                ALTER TABLE symbols 
                ADD COLUMN assembly_name VARCHAR(255);
            """))
            
            # Add index on assembly_name
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_symbols_assembly_name 
                ON symbols (assembly_name);
            """))
        
        logger.info(
            "auto_migration_completed",
            migration="add_assembly_name_to_symbols"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_assembly_name_to_symbols",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def migrate_reference_locations() -> bool:
    """
    Add location columns to relations table for Phase 3.4.
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if relations table exists
        if not await check_table_exists("relations"):
            logger.info(
                "migration_skipped",
                reason="relations table does not exist yet",
                migration="add_reference_locations"
            )
            return True
        
        # Check if start_line column already exists
        start_line_info = await get_column_info("relations", "start_line")
        if start_line_info:
            logger.info(
                "migration_not_needed",
                migration="add_reference_locations",
                message="Location columns already exist"
            )
            return True
        
        logger.info(
            "auto_migration_started",
            migration="add_reference_locations"
        )
        
        async with engine.begin() as conn:
            # Add location columns
            await conn.execute(text("""
                ALTER TABLE relations 
                ADD COLUMN start_line INTEGER,
                ADD COLUMN end_line INTEGER,
                ADD COLUMN start_column INTEGER,
                ADD COLUMN end_column INTEGER;
            """))
        
        logger.info(
            "auto_migration_completed",
            migration="add_reference_locations"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_reference_locations",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def migrate_lambda_support() -> bool:
    """
    Add columns for LINQ/Lambda analysis (Phase 3.1).
    
    Adds:
    - is_lambda, closure_variables, linq_pattern to symbols
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if symbols table exists
        if not await check_table_exists("symbols"):
            logger.info(
                "migration_skipped",
                reason="symbols table does not exist yet",
                migration="add_lambda_support"
            )
            return True
        
        # Check if is_lambda column already exists
        is_lambda_info = await get_column_info("symbols", "is_lambda")
        if is_lambda_info:
            logger.info(
                "migration_not_needed",
                migration="add_lambda_support",
                message="Lambda columns already exist"
            )
            return True
        
        logger.info(
            "auto_migration_started",
            migration="add_lambda_support"
        )
        
        async with engine.begin() as conn:
            # Add new columns
            await conn.execute(text("""
                ALTER TABLE symbols 
                ADD COLUMN is_lambda INTEGER DEFAULT 0,
                ADD COLUMN closure_variables JSONB,
                ADD COLUMN linq_pattern VARCHAR(100);
            """))
            
            # Add index on is_lambda
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_symbol_is_lambda 
                ON symbols (is_lambda);
            """))
        
        logger.info(
            "auto_migration_completed",
            migration="add_lambda_support"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_lambda_support",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def migrate_docker_services() -> bool:
    """
    Add Docker service tables (Phase 4).
    
    Adds:
    - docker_services table
    - service_repository_mappings table
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if docker_services table already exists
        if await check_table_exists("docker_services"):
            logger.info(
                "migration_not_needed",
                migration="add_docker_services",
                message="Docker services tables already exist"
            )
            return True
        
        logger.info(
            "auto_migration_started",
            migration="add_docker_services"
        )
        
        async with engine.begin() as conn:
            # Create docker_services table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS docker_services (
                    id SERIAL PRIMARY KEY,
                    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                    file_path VARCHAR(1000) NOT NULL,
                    
                    service_name VARCHAR(255) NOT NULL,
                    image VARCHAR(500),
                    container_name VARCHAR(255),
                    
                    build_context VARCHAR(1000),
                    dockerfile VARCHAR(500),
                    build_args JSONB,
                    
                    ports JSONB,
                    expose JSONB,
                    networks JSONB,
                    
                    depends_on JSONB,
                    links JSONB,
                    
                    environment JSONB,
                    volumes JSONB,
                    
                    command TEXT,
                    entrypoint TEXT,
                    working_dir VARCHAR(1000),
                    user VARCHAR(100),
                    restart VARCHAR(50),
                    
                    healthcheck JSONB,
                    labels JSONB,
                    
                    service_metadata JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    
                    CONSTRAINT uq_docker_service_repo_file_name UNIQUE (repository_id, file_path, service_name)
                )
            """))
            
            # Create indexes for docker_services
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_docker_service_repo ON docker_services(repository_id)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_docker_service_name ON docker_services(service_name)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_docker_service_image ON docker_services(image)
            """))
            
            logger.info("migration_table_created", table="docker_services")
            
            # Create service_repository_mappings table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS service_repository_mappings (
                    id SERIAL PRIMARY KEY,
                    
                    docker_service_id INTEGER REFERENCES docker_services(id) ON DELETE CASCADE,
                    service_name VARCHAR(255) NOT NULL,
                    
                    target_repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                    
                    confidence INTEGER NOT NULL,
                    mapping_method VARCHAR(50) NOT NULL,
                    mapping_metadata JSONB,
                    
                    is_manual INTEGER DEFAULT 0,
                    
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    
                    CONSTRAINT uq_service_mapping_service_repo UNIQUE (docker_service_id, target_repository_id)
                )
            """))
            
            # Create indexes for service_repository_mappings
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_service_mapping_docker_service ON service_repository_mappings(docker_service_id)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_service_mapping_target_repo ON service_repository_mappings(target_repository_id)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_service_mapping_service_name ON service_repository_mappings(service_name)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_service_mapping_confidence ON service_repository_mappings(confidence)
            """))
            
            logger.info("migration_table_created", table="service_repository_mappings")
        
        logger.info(
            "auto_migration_completed",
            migration="add_docker_services"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_docker_services",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def run_all_migrations() -> bool:
    """
    Run all auto-migrations.
    
    Returns:
        True if all migrations succeeded, False otherwise
    """
    logger.info("auto_migrations_started")
    

async def migrate_services_table() -> bool:
    """
    Migrate database to add services table and service_id to symbols (011_add_services_table).
    
    Adds:
    - services table
    - service_id to symbols table
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if repositories table exists (base requirement)
        if not await check_table_exists("repositories"):
            logger.info(
                "migration_skipped",
                reason="repositories table does not exist yet",
                migration="add_services_table"
            )
            return True
        
        # Check if services table exists
        services_table_exists = await check_table_exists("services")
        
        async with engine.begin() as conn:
            if not services_table_exists:
                logger.info("creating_services_table")
                # Create services table
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS services (
                        id SERIAL PRIMARY KEY,
                        repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                        name VARCHAR(255) NOT NULL,
                        service_type VARCHAR(50) NOT NULL,
                        description TEXT,
                        root_namespace VARCHAR(255),
                        project_path VARCHAR(1000),
                        entry_points JSONB,
                        framework_version VARCHAR(50),
                        documentation_path VARCHAR(1000),
                        last_documented_at TIMESTAMP,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    );
                """))
                
                # Create indexes for services table
                await conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_services_name 
                    ON services (name);
                """))
                
                await conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_services_repository_id 
                    ON services (repository_id);
                """))
                
                await conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_services_service_type 
                    ON services (service_type);
                """))
            
            # Add service_id to symbols table
            # Check if service_id column exists
            service_id_check = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'symbols' AND column_name = 'service_id'
                );
            """))
            service_id_exists = service_id_check.scalar()
            
            if not service_id_exists:
                logger.info("adding_service_id_to_symbols")
                await conn.execute(text("""
                    ALTER TABLE symbols 
                    ADD COLUMN service_id INTEGER REFERENCES services(id) ON DELETE SET NULL;
                """))
                
                await conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_symbols_service_id 
                    ON symbols (service_id);
                """))
            
            if services_table_exists and service_id_exists:
                 logger.info(
                    "migration_not_needed",
                    migration="add_services_table",
                    message="Services table and service_id column already exist"
                )
        
        logger.info(
            "auto_migration_completed",
            migration="add_services_table"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_services_table",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def migrate_ef_entities_table() -> bool:
    """
    Migrate database to add ef_entities table for Entity Framework Core entity mappings.
    
    Adds:
    - ef_entities table to store EF Core entity schema information
    - Indexes for efficient querying
    - Unique constraint for repository_id + entity_name
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if repositories table exists (base requirement)
        if not await check_table_exists("repositories"):
            logger.info(
                "migration_skipped",
                reason="repositories table does not exist yet",
                migration="add_ef_entities_table"
            )
            return True
        
        # Check if ef_entities table already exists
        if await check_table_exists("ef_entities"):
            logger.info(
                "migration_not_needed",
                migration="add_ef_entities_table",
                message="ef_entities table already exists"
            )
            return True
        
        logger.info(
            "auto_migration_started",
            migration="add_ef_entities_table"
        )
        
        async with engine.begin() as conn:
            # Create ef_entities table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ef_entities (
                    id SERIAL PRIMARY KEY,
                    repository_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                    entity_name VARCHAR(500) NOT NULL,
                    namespace VARCHAR(1000),
                    table_name VARCHAR(500),
                    schema_name VARCHAR(200),
                    primary_keys JSONB,
                    properties JSONB,
                    relationships JSONB,
                    raw_mapping JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
            """))
            
            # Create indexes
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_ef_entity_repo 
                ON ef_entities (repository_id);
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_ef_entity_table 
                ON ef_entities (table_name);
            """))
            
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_ef_entity_name 
                ON ef_entities (entity_name);
            """))
            
            # Create unique constraint
            await conn.execute(text("""
                ALTER TABLE ef_entities 
                ADD CONSTRAINT uq_ef_entity_repo_name 
                UNIQUE (repository_id, entity_name);
            """))
        
        logger.info(
            "auto_migration_completed",
            migration="add_ef_entities_table"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_ef_entities_table",
            error=str(e),
            error_type=type(e).__name__
        )
        return False



async def migrate_ai_enrichment() -> bool:
    """
    Add ai_enrichment column to symbols table.
    
    This column stores the AI-generated business context and enrichment data.
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if symbols table exists
        if not await check_table_exists("symbols"):
            logger.info(
                "migration_skipped",
                reason="symbols table does not exist yet",
                migration="add_ai_enrichment"
            )
            return True
        
        # Check if ai_enrichment column already exists
        ai_enrichment_info = await get_column_info("symbols", "ai_enrichment")
        if ai_enrichment_info:
            logger.info(
                "migration_not_needed",
                migration="add_ai_enrichment",
                message="ai_enrichment column already exists"
            )
            return True
        
        logger.info(
            "auto_migration_started",
            migration="add_ai_enrichment"
        )
        
        async with engine.begin() as conn:
            # Add ai_enrichment column
            await conn.execute(text("""
                ALTER TABLE symbols 
                ADD COLUMN ai_enrichment JSONB;
            """))
        
        logger.info(
            "auto_migration_completed",
            migration="add_ai_enrichment"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_ai_enrichment",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def migrate_repository_manifesto() -> bool:
    """
    Add manifesto and ai_summary columns to repositories table (Repository Aggregation).
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if repositories table exists
        if not await check_table_exists("repositories"):
            logger.info(
                "migration_skipped",
                reason="repositories table does not exist yet",
                migration="add_repository_manifesto"
            )
            return True
        
        # Check if manifesto column already exists
        manifesto_info = await get_column_info("repositories", "manifesto")
        if manifesto_info:
            logger.info(
                "migration_not_needed",
                migration="add_repository_manifesto",
                message="Repository manifesto columns already exist"
            )
            return True
        
        logger.info(
            "auto_migration_started",
            migration="add_repository_manifesto"
        )
        
        async with engine.begin() as conn:
            # Add new columns
            await conn.execute(text("""
                ALTER TABLE repositories 
                ADD COLUMN manifesto TEXT,
                ADD COLUMN ai_summary JSONB;
            """))
            
        logger.info(
            "auto_migration_completed",
            migration="add_repository_manifesto"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_repository_manifesto",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def migrate_complexity_index() -> bool:
    """
    Add index on complexity_score column in symbols table.
    
    Returns:
        True if migration was applied or not needed, False on error
    """
    try:
        # Check if symbols table exists
        if not await check_table_exists("symbols"):
            logger.info(
                "migration_skipped",
                reason="symbols table does not exist yet",
                migration="add_complexity_index"
            )
            return True
        
        # Check if index already exists
        # Note: get_indexes returns dict of index dictionaries
        indexes = await get_indexes("symbols")
        if any(idx.get("name") == "idx_symbol_complexity" for idx in indexes):
            logger.info(
                "migration_not_needed",
                migration="add_complexity_index",
                message="Index idx_symbol_complexity already exists"
            )
            return True
        
        logger.info(
            "auto_migration_started",
            migration="add_complexity_index"
        )
        
        async with engine.begin() as conn:
            # Create index
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_symbol_complexity ON symbols (complexity_score);
            """))
            
        logger.info(
            "auto_migration_completed",
            migration="add_complexity_index"
        )
        
        return True
        
    except Exception as e:
        logger.error(
            "auto_migration_failed",
            migration="add_complexity_index",
            error=str(e),
            error_type=type(e).__name__
        )
        return False


async def run_all_migrations() -> bool:
    """Run all defined migrations."""
    try:
        # Add all migrations here
        migrations = [
            ("increase_symbol_field_sizes", migrate_symbol_field_sizes),
            ("add_azuredevops_support", migrate_azuredevops_support),
            ("add_enhanced_features", migrate_enhanced_features),
            ("add_missing_relation_types", migrate_add_missing_relation_types),
            ("verify_enum_values", verify_enum_values),
            ("add_module_content_hash", migrate_module_content_hash),
            ("add_dependency_enhancements", migrate_dependency_enhancements),
            ("add_solution_parser_tables", migrate_solution_parser_tables),
            ("add_generics_support", migrate_generics_support),
            ("add_project_id_to_symbols", migrate_add_project_id_to_symbols),
            ("add_assembly_name_to_symbols", migrate_add_assembly_name_to_symbols),
            ("add_partial_class_support", migrate_partial_class_support),
            ("add_reference_locations", migrate_reference_locations),
            ("add_lambda_support", migrate_lambda_support),
            ("add_docker_services", migrate_docker_services),  # Phase 4: Docker Compose support
            ("add_services_table", migrate_services_table),  # Phase 1: Service Detection
            ("add_ef_entities_table", migrate_ef_entities_table),  # EF Core entity mappings
            ("add_ai_enrichment", migrate_ai_enrichment),  # Axon v3.2: AI Enrichment
            ("add_repository_manifesto", migrate_repository_manifesto),  # Axon v3.4: Repository Aggregation
            ("add_complexity_index", migrate_complexity_index),  # Critical for aggregation performance
        ]
        
        for migration_name, migration_func in migrations:
            success = await migration_func()
            if not success:
                logger.error(
                    "migration_failed",
                    migration=migration_name
                )
                return False
        
        logger.info("auto_migrations_completed")
        return True
        
    except Exception as e:
        logger.error(
            "auto_migrations_failed",
            error=str(e),
            error_type=type(e).__name__
        )
        return False
    finally:
        await engine.dispose()


async def main():
    """Main entry point."""
    success = await run_all_migrations()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

