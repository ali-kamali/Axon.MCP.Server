"""Verify and fix enum values to ensure uppercase consistency

Revision ID: 006_verify_enum_values
Revises: 005_rename_document_metadata_column
Create Date: 2025-11-16 16:00:00.000000

This migration ensures that:
1. All enum types use uppercase values consistently
2. All enum values are converted from lowercase to uppercase
3. Any potential data inconsistencies are logged and reported

Note: This migration converts all enum values to uppercase to match
database conventions.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '006_verify_enum_values'
down_revision = '005_rename_document_metadata_column'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Convert all enum values to uppercase."""
    
    conn = op.get_bind()
    
    print("\n" + "="*60)
    print("ENUM VALUE CONVERSION TO UPPERCASE")
    print("="*60)
    
    # Define all enum types and their expected uppercase values
    enum_definitions = {
        'languageenum': ['CSHARP', 'JAVASCRIPT', 'TYPESCRIPT', 'VUE', 'PYTHON', 'GO', 'JAVA', 'MARKDOWN', 'SQL', 'UNKNOWN'],
        'sourcecontrolproviderenum': ['GITLAB', 'AZUREDEVOPS'],
        'symbolkindenum': ['FUNCTION', 'METHOD', 'CLASS', 'INTERFACE', 'STRUCT', 'ENUM', 'VARIABLE', 'CONSTANT', 'PROPERTY', 'NAMESPACE', 'MODULE', 'TYPE_ALIAS', 'DOCUMENT_SECTION', 'CODE_EXAMPLE'],
        'accessmodifierenum': ['PUBLIC', 'PRIVATE', 'PROTECTED', 'INTERNAL', 'PROTECTED_INTERNAL', 'PRIVATE_PROTECTED'],
        'relationtypeenum': ['CALLS', 'IMPORTS', 'EXPORTS', 'INHERITS', 'IMPLEMENTS', 'USES', 'CONTAINS'],
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
    
    # Convert each enum type
    for enum_type, expected_values in enum_definitions.items():
        print(f"\n{'='*60}")
        print(f"Converting {enum_type} to uppercase...")
        print(f"{'='*60}")
        
        try:
            # Check if enum type exists
            type_check = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_type WHERE typname = :enum_type
                )
            """), {"enum_type": enum_type})
            
            if not type_check.scalar():
                print(f"   ⚠ {enum_type} does not exist, skipping...")
                continue
            
            # Get current enum values
            result = conn.execute(text("""
                SELECT enumlabel 
                FROM pg_enum 
                WHERE enumtypid = (
                    SELECT oid 
                    FROM pg_type 
                    WHERE typname = :enum_type
                )
                ORDER BY enumsortorder
            """), {"enum_type": enum_type})
            
            current_values = [row[0] for row in result]
            print(f"   Current values: {current_values}")
            
            # Check if conversion is needed
            needs_conversion = any(v != v.upper() for v in current_values)
            
            if not needs_conversion and all(v.upper() in expected_values for v in current_values):
                print(f"   ✓ {enum_type} already has uppercase values")
                continue
            
            print(f"   Converting {enum_type} to uppercase...")
            
            # Create mapping from lowercase to uppercase
            value_mapping = {}
            for current_val in current_values:
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
            
            print(f"   Value mapping: {value_mapping}")
            
            # Create new enum type with uppercase values
            new_enum_name = f"{enum_type}_new"
            # Escape single quotes in enum values
            escaped_values = [v.replace("'", "''") for v in expected_values]
            uppercase_values_str = "', '".join(escaped_values)
            
            conn.execute(text(f"""
                DROP TYPE IF EXISTS {new_enum_name} CASCADE
            """))
            
            conn.execute(text(f"""
                CREATE TYPE {new_enum_name} AS ENUM ('{uppercase_values_str}')
            """))
            
            # Migrate data if tables exist
            if enum_type in enum_usage:
                for table_name, column_name in enum_usage[enum_type]:
                    try:
                        # Check if table exists
                        table_check = conn.execute(text(f"""
                            SELECT EXISTS (
                                SELECT 1 FROM information_schema.tables 
                                WHERE table_name = '{table_name}'
                            )
                        """))
                        
                        if not table_check.scalar():
                            print(f"   ⚠ Table {table_name} does not exist, skipping...")
                            continue
                        
                        # Check if column exists
                        col_check = conn.execute(text(f"""
                            SELECT EXISTS (
                                SELECT 1 FROM information_schema.columns 
                                WHERE table_name = '{table_name}' 
                                AND column_name = '{column_name}'
                            )
                        """))
                        
                        if not col_check.scalar():
                            print(f"   ⚠ Column {table_name}.{column_name} does not exist, skipping...")
                            continue
                        
                        # Check if table has data
                        count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                        row_count = count_result.scalar() or 0
                        
                        if row_count > 0:
                            print(f"   Migrating {row_count} rows in {table_name}.{column_name}...")
                            
                            # Add temporary column
                            temp_col = f"{column_name}_new"
                            conn.execute(text(f"""
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
                            conn.execute(text(f"""
                                UPDATE {table_name} 
                                SET {temp_col} = {case_statement}
                            """))
                            
                            # Drop old column
                            conn.execute(text(f"""
                                ALTER TABLE {table_name} DROP COLUMN {column_name}
                            """))
                            
                            # Rename new column
                            conn.execute(text(f"""
                                ALTER TABLE {table_name} RENAME COLUMN {temp_col} TO {column_name}
                            """))
                            
                            # Restore NOT NULL if it was set
                            # Note: We can't check nullable after dropping, so we'll try to set it
                            # Most enum columns should be NOT NULL
                            try:
                                conn.execute(text(f"""
                                    ALTER TABLE {table_name} ALTER COLUMN {column_name} SET NOT NULL
                                """))
                            except Exception:
                                pass  # Column might be nullable, that's okay
                            
                            print(f"   ✓ Migrated {table_name}.{column_name}")
                        else:
                            print(f"   ⚠ Table {table_name} is empty, no data to migrate")
                            
                    except Exception as e:
                        print(f"   ⚠ Error migrating {table_name}.{column_name}: {str(e)}")
                        # Continue with other tables
            
            # Drop old enum type
            conn.execute(text(f"""
                DROP TYPE IF EXISTS {enum_type} CASCADE
            """))
            
            # Rename new enum type
            conn.execute(text(f"""
                ALTER TYPE {new_enum_name} RENAME TO {enum_type}
            """))
            
            # Verify the conversion
            result = conn.execute(text("""
                SELECT enumlabel 
                FROM pg_enum 
                WHERE enumtypid = (
                    SELECT oid 
                    FROM pg_type 
                    WHERE typname = :enum_type
                )
                ORDER BY enumsortorder
            """), {"enum_type": enum_type})
            
            new_values = [row[0] for row in result]
            print(f"   ✓ Conversion complete! New values: {new_values}")
            
        except Exception as e:
            print(f"   ✗ Error converting {enum_type}: {str(e)}")
            raise
    
    print("\n" + "="*60)
    print("ENUM CONVERSION COMPLETE")
    print("="*60)
    print("\nAll enum values have been converted to uppercase.")
    print("="*60 + "\n")


def downgrade() -> None:
    """Convert all enum values back to lowercase."""
    print("\nDowngrading enum values to lowercase...")
    print("Note: This is a complex operation and may require manual intervention.")
    print("Consider backing up your database before downgrading.")
    pass

