"""Add symbol enhancements: is_test, is_generated, usage_count, git_blame

Revision ID: 004_add_symbol_enhancements  
Revises: 003_add_enhanced_features
Create Date: 2025-11-13 12:00:00.000000

This migration adds additional symbol metadata fields for:
1. Test detection (is_test)
2. Generated code detection (is_generated)
3. Usage tracking (usage_count)
4. Git attribution (last_modified_by, git_blame_commit)
5. SQL language support
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004_add_symbol_enhancements'
down_revision = '003_add_enhanced_features'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema: add symbol enhancement fields."""
    
    # Add new columns to symbols table
    op.add_column('symbols', sa.Column('is_test', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('symbols', sa.Column('is_generated', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('symbols', sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('symbols', sa.Column('last_modified_by', sa.String(length=255), nullable=True))
    op.add_column('symbols', sa.Column('git_blame_commit', sa.String(length=40), nullable=True))
    
    # Add indexes for new columns
    op.create_index('idx_symbol_is_test', 'symbols', ['is_test'])
    op.create_index('idx_symbol_is_generated', 'symbols', ['is_generated'])
    op.create_index('idx_symbol_usage_count', 'symbols', ['usage_count'])
    
    # Update LanguageEnum to include SQL
    op.execute("ALTER TABLE files ALTER COLUMN language TYPE varchar(50)")
    op.execute("ALTER TABLE symbols ALTER COLUMN language TYPE varchar(50)")
    
    # Recreate language enum with SQL
    language_enum = postgresql.ENUM(
        'csharp', 'javascript', 'typescript', 'vue', 'python',
        'go', 'java', 'markdown', 'sql', 'unknown',
        name='languageenum',
        create_type=False
    )
    
    op.execute("DROP TYPE IF EXISTS languageenum CASCADE")
    language_enum.create(op.get_bind())
    
    # Apply the new enum to columns
    op.execute("""
        ALTER TABLE files 
        ALTER COLUMN language TYPE languageenum 
        USING language::languageenum
    """)
    
    op.execute("""
        ALTER TABLE symbols 
        ALTER COLUMN language TYPE languageenum 
        USING language::languageenum
    """)


def downgrade() -> None:
    """Downgrade schema: remove symbol enhancements."""
    
    # Drop indexes
    op.drop_index('idx_symbol_usage_count', table_name='symbols')
    op.drop_index('idx_symbol_is_generated', table_name='symbols')
    op.drop_index('idx_symbol_is_test', table_name='symbols')
    
    # Remove columns
    op.drop_column('symbols', 'git_blame_commit')
    op.drop_column('symbols', 'last_modified_by')
    op.drop_column('symbols', 'usage_count')
    op.drop_column('symbols', 'is_generated')
    op.drop_column('symbols', 'is_test')
    
    # Restore language enum without SQL
    op.execute("ALTER TABLE files ALTER COLUMN language TYPE varchar(50)")
    op.execute("ALTER TABLE symbols ALTER COLUMN language TYPE varchar(50)")
    
    op.execute("DROP TYPE IF EXISTS languageenum CASCADE")
    
    language_enum = postgresql.ENUM(
        'csharp', 'javascript', 'typescript', 'vue', 'python',
        'go', 'java', 'markdown', 'unknown',
        name='languageenum',
        create_type=True
    )
    
    op.execute("""
        ALTER TABLE files 
        ALTER COLUMN language TYPE languageenum 
        USING language::languageenum
    """)
    
    op.execute("""
        ALTER TABLE symbols 
        ALTER COLUMN language TYPE languageenum 
        USING language::languageenum
    """)

