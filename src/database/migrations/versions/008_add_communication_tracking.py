"""Add communication tracking tables for Phase 2

Revision ID: 008_add_communication_tracking
Revises: 007_add_module_summaries
Create Date: 2025-11-21 18:26:00.000000

This migration adds:
1. outgoing_api_calls table to track HTTP API calls (frontend→backend, backend→backend)
2. published_events table to track message queue/event bus publishing
3. event_subscriptions table to track event handlers and consumers
4. Indexes for efficient querying by repository, URL patterns, event types, etc.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '008_add_communication_tracking'
down_revision = '007_add_module_summaries'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add communication tracking tables."""
    
    print("\n" + "="*60)
    print("ADDING COMMUNICATION TRACKING TABLES (Phase 2)")
    print("="*60)
    
    # Create outgoing_api_calls table
    op.create_table(
        'outgoing_api_calls',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('symbol_id', sa.Integer(), nullable=True),
        sa.Column('repository_id', sa.Integer(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('http_method', sa.String(length=10), nullable=False),
        sa.Column('url_pattern', sa.String(length=2000), nullable=False),
        sa.Column('call_type', sa.String(length=50), nullable=False),
        sa.Column('http_client_library', sa.String(length=100), nullable=True),
        sa.Column('line_number', sa.Integer(), nullable=True),
        sa.Column('is_dynamic_url', sa.Integer(), server_default='0'),
        sa.Column('context_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    print("   ✓ Created outgoing_api_calls table")
    
    # Create indexes for outgoing_api_calls
    op.create_index('idx_api_call_repo', 'outgoing_api_calls', ['repository_id'])
    op.create_index('idx_api_call_url', 'outgoing_api_calls', ['url_pattern'])
    op.create_index('idx_api_call_symbol', 'outgoing_api_calls', ['symbol_id'])
    op.create_index('idx_api_call_type', 'outgoing_api_calls', ['call_type'])
    op.create_index('idx_api_call_method', 'outgoing_api_calls', ['http_method'])
    
    print("   ✓ Created indexes for outgoing_api_calls")
    
    # Create foreign keys for outgoing_api_calls
    op.create_foreign_key(
        'fk_api_call_symbol',
        'outgoing_api_calls', 'symbols',
        ['symbol_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_api_call_repository',
        'outgoing_api_calls', 'repositories',
        ['repository_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_api_call_file',
        'outgoing_api_calls', 'files',
        ['file_id'], ['id'],
        ondelete='CASCADE'
    )
    
    print("   ✓ Created foreign keys for outgoing_api_calls")
    
    # Create published_events table
    op.create_table(
        'published_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('symbol_id', sa.Integer(), nullable=True),
        sa.Column('repository_id', sa.Integer(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('event_type_name', sa.String(length=500), nullable=False),
        sa.Column('messaging_library', sa.String(length=100), nullable=True),
        sa.Column('topic_name', sa.String(length=500), nullable=True),
        sa.Column('exchange_name', sa.String(length=500), nullable=True),
        sa.Column('routing_key', sa.String(length=500), nullable=True),
        sa.Column('line_number', sa.Integer(), nullable=True),
        sa.Column('event_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    print("   ✓ Created published_events table")
    
    # Create indexes for published_events
    op.create_index('idx_published_event_repo', 'published_events', ['repository_id'])
    op.create_index('idx_published_event_type', 'published_events', ['event_type_name'])
    op.create_index('idx_published_event_topic', 'published_events', ['topic_name'])
    op.create_index('idx_published_event_library', 'published_events', ['messaging_library'])
    
    print("   ✓ Created indexes for published_events")
    
    # Create foreign keys for published_events
    op.create_foreign_key(
        'fk_published_event_symbol',
        'published_events', 'symbols',
        ['symbol_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_published_event_repository',
        'published_events', 'repositories',
        ['repository_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_published_event_file',
        'published_events', 'files',
        ['file_id'], ['id'],
        ondelete='CASCADE'
    )
    
    print("   ✓ Created foreign keys for published_events")
    
    # Create event_subscriptions table
    op.create_table(
        'event_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('symbol_id', sa.Integer(), nullable=False),
        sa.Column('repository_id', sa.Integer(), nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=True),
        sa.Column('event_type_name', sa.String(length=500), nullable=False),
        sa.Column('messaging_library', sa.String(length=100), nullable=True),
        sa.Column('queue_name', sa.String(length=500), nullable=True),
        sa.Column('subscription_pattern', sa.String(length=500), nullable=True),
        sa.Column('line_number', sa.Integer(), nullable=True),
        sa.Column('handler_class_name', sa.String(length=500), nullable=True),
        sa.Column('handler_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    print("   ✓ Created event_subscriptions table")
    
    # Create indexes for event_subscriptions
    op.create_index('idx_event_sub_repo', 'event_subscriptions', ['repository_id'])
    op.create_index('idx_event_sub_type', 'event_subscriptions', ['event_type_name'])
    op.create_index('idx_event_sub_queue', 'event_subscriptions', ['queue_name'])
    op.create_index('idx_event_sub_library', 'event_subscriptions', ['messaging_library'])
    op.create_index('idx_event_sub_symbol', 'event_subscriptions', ['symbol_id'])
    
    print("   ✓ Created indexes for event_subscriptions")
    
    # Create foreign keys for event_subscriptions
    op.create_foreign_key(
        'fk_event_sub_symbol',
        'event_subscriptions', 'symbols',
        ['symbol_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_event_sub_repository',
        'event_subscriptions', 'repositories',
        ['repository_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_event_sub_file',
        'event_subscriptions', 'files',
        ['file_id'], ['id'],
        ondelete='CASCADE'
    )
    
    print("   ✓ Created foreign keys for event_subscriptions")
    
    print("\n" + "="*60)
    print("COMMUNICATION TRACKING TABLES CREATED SUCCESSFULLY")
    print("="*60)
    print("\nThe tables are ready for storing:")
    print("  - Frontend→Backend API calls")
    print("  - Backend→Backend microservice communication")
    print("  - Event publishing and subscriptions")
    print("="*60 + "\n")


def downgrade() -> None:
    """Remove communication tracking tables."""
    
    print("\nRemoving communication tracking tables...")
    
    # Drop event_subscriptions
    op.drop_constraint('fk_event_sub_file', 'event_subscriptions', type_='foreignkey')
    op.drop_constraint('fk_event_sub_repository', 'event_subscriptions', type_='foreignkey')
    op.drop_constraint('fk_event_sub_symbol', 'event_subscriptions', type_='foreignkey')
    op.drop_index('idx_event_sub_symbol', table_name='event_subscriptions')
    op.drop_index('idx_event_sub_library', table_name='event_subscriptions')
    op.drop_index('idx_event_sub_queue', table_name='event_subscriptions')
    op.drop_index('idx_event_sub_type', table_name='event_subscriptions')
    op.drop_index('idx_event_sub_repo', table_name='event_subscriptions')
    op.drop_table('event_subscriptions')
    print("   ✓ Removed event_subscriptions table")
    
    # Drop published_events
    op.drop_constraint('fk_published_event_file', 'published_events', type_='foreignkey')
    op.drop_constraint('fk_published_event_repository', 'published_events', type_='foreignkey')
    op.drop_constraint('fk_published_event_symbol', 'published_events', type_='foreignkey')
    op.drop_index('idx_published_event_library', table_name='published_events')
    op.drop_index('idx_published_event_topic', table_name='published_events')
    op.drop_index('idx_published_event_type', table_name='published_events')
    op.drop_index('idx_published_event_repo', table_name='published_events')
    op.drop_table('published_events')
    print("   ✓ Removed published_events table")
    
    # Drop outgoing_api_calls
    op.drop_constraint('fk_api_call_file', 'outgoing_api_calls', type_='foreignkey')
    op.drop_constraint('fk_api_call_repository', 'outgoing_api_calls', type_='foreignkey')
    op.drop_constraint('fk_api_call_symbol', 'outgoing_api_calls', type_='foreignkey')
    op.drop_index('idx_api_call_method', table_name='outgoing_api_calls')
    op.drop_index('idx_api_call_type', table_name='outgoing_api_calls')
    op.drop_index('idx_api_call_symbol', table_name='outgoing_api_calls')
    op.drop_index('idx_api_call_url', table_name='outgoing_api_calls')
    op.drop_index('idx_api_call_repo', table_name='outgoing_api_calls')
    op.drop_table('outgoing_api_calls')
    print("   ✓ Removed outgoing_api_calls table")
    
    print("\nCommunication tracking tables removed successfully")
