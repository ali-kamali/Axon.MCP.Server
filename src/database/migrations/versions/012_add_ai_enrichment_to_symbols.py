"""Add ai_enrichment to symbols

Revision ID: 012
Revises: 011
Create Date: 2025-12-12 18:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add ai_enrichment column to symbols
    op.add_column('symbols', sa.Column('ai_enrichment', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    # Remove ai_enrichment column from symbols
    op.drop_column('symbols', 'ai_enrichment')
