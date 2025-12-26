"""Add services table and service_id to symbols

Revision ID: 011
Revises: add_module_content_hash
Create Date: 2025-12-03 23:55:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '011'
down_revision = 'add_module_content_hash'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create services table
    op.create_table('services',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('repository_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('service_type', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('root_namespace', sa.String(length=255), nullable=True),
        sa.Column('project_path', sa.String(length=1000), nullable=True),
        sa.Column('entry_points', sa.JSON(), nullable=True),
        sa.Column('framework_version', sa.String(length=50), nullable=True),
        sa.Column('documentation_path', sa.String(length=1000), nullable=True),
        sa.Column('last_documented_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['repository_id'], ['repositories.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_services_name'), 'services', ['name'], unique=False)
    op.create_index(op.f('ix_services_repository_id'), 'services', ['repository_id'], unique=False)
    op.create_index(op.f('ix_services_service_type'), 'services', ['service_type'], unique=False)

    # Add service_id to symbols
    op.add_column('symbols', sa.Column('service_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_symbols_service_id'), 'symbols', ['service_id'], unique=False)
    op.create_foreign_key(None, 'symbols', 'services', ['service_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    # Remove service_id from symbols
    op.drop_constraint(None, 'symbols', type_='foreignkey')
    op.drop_index(op.f('ix_symbols_service_id'), table_name='symbols')
    op.drop_column('symbols', 'service_id')

    # Drop services table
    op.drop_index(op.f('ix_services_service_type'), table_name='services')
    op.drop_index(op.f('ix_services_repository_id'), table_name='services')
    op.drop_index(op.f('ix_services_name'), table_name='services')
    op.drop_table('services')
