"""Rename documents.metadata to documents.doc_metadata

Revision ID: 005_rename_document_metadata_column
Revises: 004_add_symbol_enhancements
Create Date: 2025-11-13 15:00:00.000000

This migration renames the 'metadata' column in the documents table to 'doc_metadata'
to avoid conflicts with SQLAlchemy's reserved 'metadata' attribute.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '005_rename_document_metadata_column'
down_revision = '004_add_symbol_enhancements'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Rename metadata column to doc_metadata."""
    # Rename the column
    op.alter_column(
        'documents',
        'metadata',
        new_column_name='doc_metadata',
        existing_type=sa.JSON(),
        existing_nullable=True
    )


def downgrade() -> None:
    """Rename doc_metadata column back to metadata."""
    # Rename the column back
    op.alter_column(
        'documents',
        'doc_metadata',
        new_column_name='metadata',
        existing_type=sa.JSON(),
        existing_nullable=True
    )

