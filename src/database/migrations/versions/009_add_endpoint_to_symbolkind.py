"""Add ENDPOINT to symbolkindenum

Revision ID: 009_add_endpoint_to_symbolkind
Revises: 008_add_communication_tracking
Create Date: 2025-11-22 12:30:00.000000

This migration adds 'ENDPOINT' to the symbolkindenum type.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '009_add_endpoint_to_symbolkind'
down_revision = '008_add_communication_tracking'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add ENDPOINT to symbolkindenum."""
    
    print("\n" + "="*60)
    print("ADDING ENDPOINT TO SYMBOLKINDENUM")
    print("="*60)
    
    # We need to recreate the enum to add a value in a transaction-safe way
    # that works with Alembic's transaction model
    
    # 1. Rename the column to a temporary name to free up the enum usage
    op.execute("ALTER TABLE symbols ALTER COLUMN kind TYPE varchar(50)")
    
    # 2. Create the new enum type
    symbol_kind_enum = postgresql.ENUM(
        'FUNCTION', 'METHOD', 'CLASS', 'INTERFACE', 'STRUCT', 'ENUM',
        'VARIABLE', 'CONSTANT', 'PROPERTY', 'NAMESPACE', 'MODULE',
        'TYPE_ALIAS', 'DOCUMENT_SECTION', 'CODE_EXAMPLE', 'ENDPOINT',
        name='symbolkindenum',
        create_type=False
    )
    
    # 3. Drop the old enum type
    op.execute("DROP TYPE IF EXISTS symbolkindenum CASCADE")
    
    # 4. Create the new enum type
    symbol_kind_enum.create(op.get_bind())
    
    # 5. Convert the column back to the enum type
    op.execute("""
        ALTER TABLE symbols 
        ALTER COLUMN kind TYPE symbolkindenum 
        USING kind::symbolkindenum
    """)
    
    print("   ✓ Added ENDPOINT to symbolkindenum")
    print("="*60 + "\n")


def downgrade() -> None:
    """Remove ENDPOINT from symbolkindenum."""
    
    print("\nRemoving ENDPOINT from symbolkindenum...")
    
    # 1. Convert column to varchar
    op.execute("ALTER TABLE symbols ALTER COLUMN kind TYPE varchar(50)")
    
    # 2. Create the original enum type (without ENDPOINT)
    symbol_kind_enum = postgresql.ENUM(
        'FUNCTION', 'METHOD', 'CLASS', 'INTERFACE', 'STRUCT', 'ENUM',
        'VARIABLE', 'CONSTANT', 'PROPERTY', 'NAMESPACE', 'MODULE',
        'TYPE_ALIAS', 'DOCUMENT_SECTION', 'CODE_EXAMPLE',
        name='symbolkindenum',
        create_type=False
    )
    
    # 3. Drop the current enum type
    op.execute("DROP TYPE IF EXISTS symbolkindenum CASCADE")
    
    # 4. Create the original enum type
    symbol_kind_enum.create(op.get_bind())
    
    # 5. Convert the column back to the enum type
    # Note: This will fail if there are any 'ENDPOINT' values in the table
    # We'll map them to 'METHOD' as a fallback
    op.execute("""
        UPDATE symbols SET kind = 'METHOD' WHERE kind = 'ENDPOINT'
    """)
    
    op.execute("""
        ALTER TABLE symbols 
        ALTER COLUMN kind TYPE symbolkindenum 
        USING kind::symbolkindenum
    """)
    
    print("   ✓ Removed ENDPOINT from symbolkindenum")
