"""Add module_summaries table for Phase 2: Aggregated Context

Revision ID: 007_add_module_summaries
Revises: 006_verify_enum_values
Create Date: 2025-11-20 10:00:00.000000

This migration adds:
1. module_summaries table to store AI-generated module summaries
2. Indexes for efficient querying by repository and path
3. Support for tracking module metadata and entry points
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '007_add_module_summaries'
down_revision = '006_verify_enum_values'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add module_summaries table."""
    
    print("\n" + "="*60)
    print("ADDING MODULE_SUMMARIES TABLE (Phase 2)")
    print("="*60)
    
    # Create module_summaries table
    op.create_table(
        'module_summaries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('repository_id', sa.Integer(), nullable=False),
        sa.Column('module_path', sa.String(length=1000), nullable=False),
        sa.Column('module_name', sa.String(length=255), nullable=False),
        sa.Column('module_type', sa.String(length=50), nullable=False),
        sa.Column('is_package', sa.Integer(), server_default='0'),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('purpose', sa.Text(), nullable=True),
        sa.Column('key_components', sa.JSON(), nullable=True),
        sa.Column('dependencies', sa.JSON(), nullable=True),
        sa.Column('entry_points', sa.JSON(), nullable=True),
        sa.Column('file_count', sa.Integer(), server_default='0'),
        sa.Column('symbol_count', sa.Integer(), server_default='0'),
        sa.Column('line_count', sa.Integer(), server_default='0'),
        sa.Column('complexity_score', sa.Integer(), nullable=True),
        sa.Column('generated_by', sa.String(length=100), nullable=True),
        sa.Column('generated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('last_updated', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('version', sa.Integer(), server_default='1'),
        sa.PrimaryKeyConstraint('id')
    )
    
    print("   ✓ Created module_summaries table")
    
    # Create indexes
    op.create_index(
        'idx_module_repo_path',
        'module_summaries',
        ['repository_id', 'module_path']
    )
    print("   ✓ Created index idx_module_repo_path")
    
    op.create_index(
        'idx_module_type',
        'module_summaries',
        ['module_type', 'repository_id']
    )
    print("   ✓ Created index idx_module_type")
    
    op.create_index(
        'idx_module_name',
        'module_summaries',
        ['module_name']
    )
    print("   ✓ Created index idx_module_name")
    
    op.create_index(
        'idx_module_repository',
        'module_summaries',
        ['repository_id']
    )
    print("   ✓ Created index idx_module_repository")
    
    # Create foreign key constraint
    op.create_foreign_key(
        'fk_module_summaries_repository',
        'module_summaries', 'repositories',
        ['repository_id'], ['id'],
        ondelete='CASCADE'
    )
    print("   ✓ Created foreign key to repositories table")
    
    print("\n" + "="*60)
    print("MODULE_SUMMARIES TABLE CREATED SUCCESSFULLY")
    print("="*60)
    print("\nThe table is ready for storing AI-generated module summaries.")
    print("="*60 + "\n")


def downgrade() -> None:
    """Remove module_summaries table."""
    
    print("\nRemoving module_summaries table...")
    
    # Drop foreign key
    op.drop_constraint('fk_module_summaries_repository', 'module_summaries', type_='foreignkey')
    
    # Drop indexes
    op.drop_index('idx_module_repository', table_name='module_summaries')
    op.drop_index('idx_module_name', table_name='module_summaries')
    op.drop_index('idx_module_type', table_name='module_summaries')
    op.drop_index('idx_module_repo_path', table_name='module_summaries')
    
    # Drop table
    op.drop_table('module_summaries')
    
    print("   ✓ module_summaries table removed")

