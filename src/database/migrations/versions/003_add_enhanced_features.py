"""Add enhanced features: structured docs, attributes, config, dependencies, documents

Revision ID: 003_add_enhanced_features
Revises: 002_add_azuredevops_support
Create Date: 2025-11-13 00:00:00.000000

This migration adds comprehensive enhancements to support:
1. Structured documentation (XML/JSDoc) in symbols
2. Attributes (C# attributes, TypeScript decorators) in symbols
3. Enhanced chunking with chunk_subtype and context_metadata
4. Configuration entries table for appsettings.json
5. Dependencies table for package management
6. Project references table for .csproj relationships
7. Documents table for markdown documentation
8. New symbol kinds (DOCUMENT_SECTION, CODE_EXAMPLE)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_add_enhanced_features'
down_revision = '002_add_azuredevops_support'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema: add enhanced features."""
    
    # Add new columns to symbols table
    op.add_column('symbols', sa.Column('structured_docs', sa.JSON(), nullable=True))
    op.add_column('symbols', sa.Column('attributes', sa.JSON(), nullable=True))
    op.add_column('symbols', sa.Column('parent_name', sa.String(length=2000), nullable=True))
    op.add_column('symbols', sa.Column('complexity_score', sa.Integer(), nullable=True))
    
    # Add new columns to chunks table
    op.add_column('chunks', sa.Column('chunk_subtype', sa.String(length=50), nullable=True))
    op.add_column('chunks', sa.Column('parent_chunk_id', sa.Integer(), nullable=True))
    op.add_column('chunks', sa.Column('context_metadata', sa.JSON(), nullable=True))
    
    # Add foreign key for parent_chunk_id
    op.create_foreign_key(
        'fk_chunks_parent_chunk',
        'chunks', 'chunks',
        ['parent_chunk_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # Create index on parent_chunk_id
    op.create_index('ix_chunks_parent_chunk_id', 'chunks', ['parent_chunk_id'])
    
    # Update SymbolKindEnum to include new types
    # First drop the existing enum constraint
    op.execute("ALTER TABLE symbols ALTER COLUMN kind TYPE varchar(50)")
    
    # Recreate the enum with new values
    symbol_kind_enum = postgresql.ENUM(
        'function', 'method', 'class', 'interface', 'struct', 'enum',
        'variable', 'constant', 'property', 'namespace', 'module',
        'type_alias', 'document_section', 'code_example',
        name='symbolkindenum',
        create_type=False
    )
    
    # Drop old enum if exists and create new one
    op.execute("DROP TYPE IF EXISTS symbolkindenum CASCADE")
    symbol_kind_enum.create(op.get_bind())
    
    # Apply the new enum type to the column
    op.execute("""
        ALTER TABLE symbols 
        ALTER COLUMN kind TYPE symbolkindenum 
        USING kind::symbolkindenum
    """)
    
    # Create documents table
    op.create_table(
        'documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('repository_id', sa.Integer(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('path', sa.String(length=1000), nullable=False),
        sa.Column('doc_type', sa.String(length=50), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('sections', sa.JSON(), nullable=True),
        sa.Column('code_examples', sa.JSON(), nullable=True),
        sa.Column('doc_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['file_id'], ['files.id'], ondelete='CASCADE')
    )
    
    op.create_index('idx_document_repo_type', 'documents', ['repository_id', 'doc_type'])
    op.create_index('idx_document_path', 'documents', ['path'])
    
    # Create configuration_entries table
    op.create_table(
        'configuration_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('repository_id', sa.Integer(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('config_key', sa.String(length=500), nullable=False),
        sa.Column('config_value', sa.Text(), nullable=True),
        sa.Column('config_type', sa.String(length=50), nullable=True),
        sa.Column('environment', sa.String(length=50), nullable=True),
        sa.Column('is_secret', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('file_path', sa.String(length=1000), nullable=True),
        sa.Column('line_number', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['file_id'], ['files.id'], ondelete='CASCADE')
    )
    
    op.create_index('idx_config_key', 'configuration_entries', ['config_key'])
    op.create_index('idx_config_repo_env', 'configuration_entries', ['repository_id', 'environment'])
    op.create_index('idx_config_secret', 'configuration_entries', ['is_secret'])
    
    # Create dependencies table
    op.create_table(
        'dependencies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('repository_id', sa.Integer(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('package_name', sa.String(length=255), nullable=False),
        sa.Column('package_version', sa.String(length=100), nullable=True),
        sa.Column('dependency_type', sa.String(length=50), nullable=True),
        sa.Column('is_dev_dependency', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('file_path', sa.String(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['file_id'], ['files.id'], ondelete='CASCADE')
    )
    
    op.create_index('idx_dep_package', 'dependencies', ['package_name'])
    op.create_index('idx_dep_repo_type', 'dependencies', ['repository_id', 'dependency_type'])
    
    # Create project_references table
    op.create_table(
        'project_references',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('repository_id', sa.Integer(), nullable=False),
        sa.Column('source_project_path', sa.String(length=1000), nullable=False),
        sa.Column('target_project_path', sa.String(length=1000), nullable=False),
        sa.Column('reference_type', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ondelete='CASCADE')
    )
    
    op.create_index('idx_proj_ref_repo', 'project_references', ['repository_id'])
    op.create_index('idx_proj_ref_source', 'project_references', ['source_project_path'])
    
    # Update LanguageEnum to include markdown
    op.execute("ALTER TABLE files ALTER COLUMN language TYPE varchar(50)")
    op.execute("ALTER TABLE symbols ALTER COLUMN language TYPE varchar(50)")
    
    # Recreate language enum with markdown
    language_enum = postgresql.ENUM(
        'csharp', 'javascript', 'typescript', 'vue', 'python',
        'go', 'java', 'markdown', 'unknown',
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
    """Downgrade schema: remove enhanced features."""
    
    # Drop new tables
    op.drop_table('project_references')
    op.drop_table('dependencies')
    op.drop_table('configuration_entries')
    op.drop_table('documents')
    
    # Remove new columns from chunks
    op.drop_constraint('fk_chunks_parent_chunk', 'chunks', type_='foreignkey')
    op.drop_index('ix_chunks_parent_chunk_id', table_name='chunks')
    op.drop_column('chunks', 'context_metadata')
    op.drop_column('chunks', 'parent_chunk_id')
    op.drop_column('chunks', 'chunk_subtype')
    
    # Remove new columns from symbols
    op.drop_column('symbols', 'complexity_score')
    op.drop_column('symbols', 'parent_name')
    op.drop_column('symbols', 'attributes')
    op.drop_column('symbols', 'structured_docs')
    
    # Restore original enums (without new values)
    # This is a simplified downgrade - in production you might want to preserve data
    op.execute("ALTER TABLE symbols ALTER COLUMN kind TYPE varchar(50)")
    op.execute("ALTER TABLE files ALTER COLUMN language TYPE varchar(50)")
    op.execute("ALTER TABLE symbols ALTER COLUMN language TYPE varchar(50)")
    
    # Recreate original enums
    op.execute("DROP TYPE IF EXISTS symbolkindenum CASCADE")
    op.execute("DROP TYPE IF EXISTS languageenum CASCADE")
    
    symbol_kind_enum = postgresql.ENUM(
        'function', 'method', 'class', 'interface', 'struct', 'enum',
        'variable', 'constant', 'property', 'namespace', 'module', 'type_alias',
        name='symbolkindenum',
        create_type=True
    )
    
    language_enum = postgresql.ENUM(
        'csharp', 'javascript', 'typescript', 'vue', 'python',
        'go', 'java', 'unknown',
        name='languageenum',
        create_type=True
    )
    
    op.execute("""
        ALTER TABLE symbols 
        ALTER COLUMN kind TYPE symbolkindenum 
        USING kind::symbolkindenum
    """)
    
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

