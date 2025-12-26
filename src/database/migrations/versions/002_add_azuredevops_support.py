"""Add Azure DevOps support to repositories

Revision ID: 002_add_azuredevops_support
Revises: 001_increase_symbol_field_sizes
Create Date: 2025-11-12 21:30:00.000000

This migration adds support for multiple source control providers by:
1. Adding a provider enum column to repositories table
2. Adding Azure DevOps specific fields
3. Making GitLab project_id nullable
4. Adding clone_url field for both providers
5. Setting default provider to 'gitlab' for existing repositories
6. Adding appropriate indexes for the new fields
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '002_add_azuredevops_support'
down_revision = '001_increase_symbol_field_sizes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema: add Azure DevOps support."""
    
    # Create the source control provider enum
    provider_enum = postgresql.ENUM('gitlab', 'azuredevops', name='sourcecontrolproviderenum')
    provider_enum.create(op.get_bind())
    
    # Add provider column with default value 'gitlab'
    op.add_column('repositories', sa.Column('provider', provider_enum, nullable=False, server_default='gitlab'))
    
    # Add Azure DevOps specific fields
    op.add_column('repositories', sa.Column('azuredevops_project_name', sa.String(length=255), nullable=True))
    op.add_column('repositories', sa.Column('azuredevops_repo_id', sa.String(length=255), nullable=True))
    
    # Add clone_url field for both providers
    op.add_column('repositories', sa.Column('clone_url', sa.String(length=500), nullable=True))
    
    # Update existing repositories to populate clone_url from url field
    connection = op.get_bind()
    connection.execute(sa.text("UPDATE repositories SET clone_url = url WHERE clone_url IS NULL"))
    
    # Make clone_url non-nullable after populating existing data
    op.alter_column('repositories', 'clone_url', nullable=False)
    
    # Make gitlab_project_id nullable since Azure DevOps repos won't have it
    op.alter_column('repositories', 'gitlab_project_id', nullable=True)
    
    # Remove the unique constraint on gitlab_project_id since it will be null for Azure DevOps repos
    op.drop_constraint('repositories_gitlab_project_id_key', 'repositories', type_='unique')
    
    # Create new indexes for the provider-specific fields
    op.create_index('idx_repo_provider_path', 'repositories', ['provider', 'path_with_namespace'])
    op.create_index('idx_repo_gitlab_project', 'repositories', ['gitlab_project_id'])
    op.create_index('idx_repo_azuredevops_project_repo', 'repositories', ['azuredevops_project_name', 'azuredevops_repo_id'])
    
    # Add provider to the existing status index
    op.drop_index('idx_repo_status_updated', table_name='repositories')
    op.create_index('idx_repo_provider_status_updated', 'repositories', ['provider', 'status', 'updated_at'])


def downgrade() -> None:
    """Downgrade schema: remove Azure DevOps support."""
    
    # Drop the new indexes
    op.drop_index('idx_repo_provider_status_updated', table_name='repositories')
    op.drop_index('idx_repo_azuredevops_project_repo', table_name='repositories')
    op.drop_index('idx_repo_gitlab_project', table_name='repositories')
    op.drop_index('idx_repo_provider_path', table_name='repositories')
    
    # Recreate the original status index
    op.create_index('idx_repo_status_updated', 'repositories', ['status', 'updated_at'])
    
    # Remove Azure DevOps repositories before making gitlab_project_id non-nullable
    connection = op.get_bind()
    connection.execute(sa.text("DELETE FROM repositories WHERE provider = 'azuredevops'"))
    
    # Make gitlab_project_id non-nullable again
    op.alter_column('repositories', 'gitlab_project_id', nullable=False)
    
    # Recreate the unique constraint on gitlab_project_id
    op.create_unique_constraint('repositories_gitlab_project_id_key', 'repositories', ['gitlab_project_id'])
    
    # Remove the new columns
    op.drop_column('repositories', 'clone_url')
    op.drop_column('repositories', 'azuredevops_repo_id')
    op.drop_column('repositories', 'azuredevops_project_name')
    op.drop_column('repositories', 'provider')
    
    # Drop the enum type
    provider_enum = postgresql.ENUM('gitlab', 'azuredevops', name='sourcecontrolproviderenum')
    provider_enum.drop(op.get_bind())
