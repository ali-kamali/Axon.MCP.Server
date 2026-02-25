"""Add GitHub support to repositories

Revision ID: 016_add_github_support
Revises: 015_add_complexity_index
Create Date: 2026-02-25 00:00:00.000000

This migration adds support for GitHub as a source control provider by:
1. Adding 'github' value to the sourcecontrolproviderenum enum type
2. Adding GitHub-specific fields to the repositories table
3. Adding a composite index on github_owner + github_repo_name
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '016_add_github_support'
down_revision = '015_add_complexity_index'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema: add GitHub support."""

    # Add 'github' value to the existing sourcecontrolproviderenum enum
    # PostgreSQL requires ALTER TYPE to add new enum values
    op.execute("ALTER TYPE sourcecontrolproviderenum ADD VALUE IF NOT EXISTS 'GITHUB'")

    # Add GitHub-specific columns to repositories table
    op.add_column('repositories', sa.Column('github_owner', sa.String(length=255), nullable=True))
    op.add_column('repositories', sa.Column('github_repo_name', sa.String(length=255), nullable=True))
    op.add_column('repositories', sa.Column('github_repo_id', sa.BigInteger(), nullable=True))

    # Create indexes for GitHub fields
    op.create_index('idx_repo_github_owner', 'repositories', ['github_owner'])
    op.create_index('idx_repo_github_repo_name', 'repositories', ['github_repo_name'])
    op.create_index('idx_repo_github_repo_id', 'repositories', ['github_repo_id'])
    op.create_index('idx_repo_github_owner_repo', 'repositories', ['github_owner', 'github_repo_name'])


def downgrade() -> None:
    """Downgrade schema: remove GitHub support."""

    # Remove GitHub repositories before removing enum value
    connection = op.get_bind()
    connection.execute(sa.text("DELETE FROM repositories WHERE provider = 'GITHUB'"))

    # Drop indexes
    op.drop_index('idx_repo_github_owner_repo', table_name='repositories')
    op.drop_index('idx_repo_github_repo_id', table_name='repositories')
    op.drop_index('idx_repo_github_repo_name', table_name='repositories')
    op.drop_index('idx_repo_github_owner', table_name='repositories')

    # Drop columns
    op.drop_column('repositories', 'github_repo_id')
    op.drop_column('repositories', 'github_repo_name')
    op.drop_column('repositories', 'github_owner')

    # Note: PostgreSQL does not support removing enum values.
    # The 'GITHUB' value will remain in the enum type but is harmless.
