"""Add index on Symbol.complexity_score

Revision ID: 015_add_complexity_index
Revises: 014_add_repository_manifesto
Create Date: 2024-12-12 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '015_add_complexity_index'
down_revision = '014_add_repository_manifesto'
branch_labels = None
depends_on = None

def upgrade():
    # Create index on complexity_score for faster aggregation sorting
    # We use 'concurrently=True' in raw SQL usually, but Alembic op.create_index 
    # supports postgresql_concurrently=True if we want.
    # For now, standard index creation is fine.
    op.create_index(
        'idx_symbol_complexity',
        'symbols',
        ['complexity_score'],
        unique=False
    )

def downgrade():
    op.drop_index('idx_symbol_complexity', table_name='symbols')
