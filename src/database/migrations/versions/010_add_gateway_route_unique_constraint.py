"""Add unique constraint to gateway_routes table.

Revision ID: 010
Revises: 009
Create Date: 2024-11-25

This migration adds a unique constraint to prevent duplicate gateway routes.
A route is unique per repository + file + downstream path + gateway type.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add unique constraint to gateway_routes table."""
    # First, remove any existing duplicates (keep the most recent one)
    # This is a safety measure before adding the constraint
    op.execute("""
        DELETE FROM gateway_routes g1
        WHERE g1.id NOT IN (
            SELECT MAX(g2.id)
            FROM gateway_routes g2
            GROUP BY g2.repository_id, g2.file_path, g2.downstream_path_template, g2.gateway_type
        )
    """)
    
    # Add the unique constraint
    op.create_unique_constraint(
        'uq_gateway_route_repo_file_path_type',
        'gateway_routes',
        ['repository_id', 'file_path', 'downstream_path_template', 'gateway_type']
    )


def downgrade() -> None:
    """Remove unique constraint from gateway_routes table."""
    op.drop_constraint(
        'uq_gateway_route_repo_file_path_type',
        'gateway_routes',
        type_='unique'
    )

