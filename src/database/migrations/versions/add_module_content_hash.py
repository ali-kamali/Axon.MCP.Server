"""Add content_hash to module_summaries

Revision ID: add_module_content_hash
Revises: 
Create Date: 2025-11-27 02:11:11.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_module_content_hash'
down_revision = '010_add_gateway_route_unique_constraint'
depends_on = None


def upgrade():
    """Add content_hash column to module_summaries table."""
    op.add_column('module_summaries', sa.Column('content_hash', sa.String(length=64), nullable=True))


def downgrade():
    """Remove content_hash column from module_summaries table."""
    op.drop_column('module_summaries', 'content_hash')
