"""Increase symbol field sizes to prevent truncation

Revision ID: 001_increase_symbol_field_sizes
Revises: 
Create Date: 2025-11-10 21:00:00.000000

This migration increases the VARCHAR field sizes in the symbols table to prevent
data truncation errors when parsing code with long type names or qualified names.

Changes:
- name: VARCHAR(500) -> VARCHAR(1000)
- fully_qualified_name: VARCHAR(1000) -> VARCHAR(2000)
- return_type: VARCHAR(255) -> VARCHAR(1000)
- signature: VARCHAR(255) -> TEXT (if needed)
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001_increase_symbol_field_sizes'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema: increase VARCHAR field sizes."""
    # Increase name field from VARCHAR(500) to VARCHAR(1000)
    op.alter_column(
        'symbols',
        'name',
        existing_type=sa.String(length=500),
        type_=sa.String(length=1000),
        existing_nullable=False
    )
    
    # Increase fully_qualified_name field from VARCHAR(1000) to VARCHAR(2000)
    op.alter_column(
        'symbols',
        'fully_qualified_name',
        existing_type=sa.String(length=1000),
        type_=sa.String(length=2000),
        existing_nullable=True
    )
    
    # Increase return_type field from VARCHAR(255) to VARCHAR(1000)
    op.alter_column(
        'symbols',
        'return_type',
        existing_type=sa.String(length=255),
        type_=sa.String(length=1000),
        existing_nullable=True
    )
    
    # Convert signature field from VARCHAR(255) to TEXT if it's currently VARCHAR
    # Check if signature column exists and is VARCHAR before converting
    # Note: This uses raw SQL to check and convert, as Alembic doesn't easily
    # support conditional type changes
    connection = op.get_bind()
    result = connection.execute(sa.text("""
        SELECT data_type 
        FROM information_schema.columns 
        WHERE table_name = 'symbols' 
        AND column_name = 'signature'
    """))
    row = result.fetchone()
    if row and row[0] in ('character varying', 'varchar'):
        # Convert VARCHAR to TEXT
        op.alter_column(
            'symbols',
            'signature',
            existing_type=sa.String(length=255),
            type_=sa.Text(),
            existing_nullable=True
        )


def downgrade() -> None:
    """Downgrade schema: revert VARCHAR field sizes."""
    # Note: Downgrading may cause data loss if any values exceed the old limits
    
    # Revert signature field from TEXT to VARCHAR(255) if it was converted
    connection = op.get_bind()
    result = connection.execute(sa.text("""
        SELECT data_type 
        FROM information_schema.columns 
        WHERE table_name = 'symbols' 
        AND column_name = 'signature'
    """))
    row = result.fetchone()
    if row and row[0] == 'text':
        # Revert TEXT to VARCHAR(255)
        op.alter_column(
            'symbols',
            'signature',
            existing_type=sa.Text(),
            type_=sa.String(length=255),
            existing_nullable=True
        )
    
    # Revert return_type field from VARCHAR(1000) to VARCHAR(255)
    op.alter_column(
        'symbols',
        'return_type',
        existing_type=sa.String(length=1000),
        type_=sa.String(length=255),
        existing_nullable=True
    )
    
    # Revert fully_qualified_name field from VARCHAR(2000) to VARCHAR(1000)
    op.alter_column(
        'symbols',
        'fully_qualified_name',
        existing_type=sa.String(length=2000),
        type_=sa.String(length=1000),
        existing_nullable=True
    )
    
    # Revert name field from VARCHAR(1000) to VARCHAR(500)
    op.alter_column(
        'symbols',
        'name',
        existing_type=sa.String(length=1000),
        type_=sa.String(length=500),
        existing_nullable=False
    )

