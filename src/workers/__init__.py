"""
Background workers package for Axon MCP Server.

This package provides Celery-based distributed task processing for:
- Repository synchronization
- File parsing
- Knowledge extraction
- Embedding generation
"""

from src.workers.celery_app import celery_app
from src.workers.tasks import (
    sync_repository,
    parse_file_task,
    generate_embeddings_task,
    enrich_batch,
    generate_context,
    aggregate_repository_summary,
)
from src.workers.distributed_lock import DistributedLock, get_distributed_lock
from src.workers.job_monitor import JobMonitor

__all__ = [
    'celery_app',
    'sync_repository',
    'parse_file_task',
    'generate_embeddings_task',
    'enrich_batch',
    'generate_context',
    'aggregate_repository_summary',
    'DistributedLock',
    'get_distributed_lock',
    'JobMonitor',
]


