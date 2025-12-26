"""Add manifesto and ai_summary to repositories table

Revision ID: 014
Revises: 013
Create Date: 2025-12-12 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add manifesto and ai_summary columns to repositories table
    op.add_column('repositories', sa.Column('manifesto', sa.Text(), nullable=True))
    op.add_column('repositories', sa.Column('ai_summary', postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    # Remove columns in reverse order
    op.drop_column('repositories', 'ai_summary')
    op.drop_column('repositories', 'manifesto')
