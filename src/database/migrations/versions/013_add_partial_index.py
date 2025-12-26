"""Add partial index for unenriched symbols

Revision ID: 013
Revises: 012
Create Date: 2025-12-12 20:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add partial index to speed up finding symbols that need enrichment
    op.create_index(
        'idx_symbols_unenriched',
        'symbols',
        ['id'],
        postgresql_where=sa.text('ai_enrichment IS NULL')
    )


def downgrade() -> None:
    op.drop_index('idx_symbols_unenriched', table_name='symbols')
