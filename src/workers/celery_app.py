"""
Celery application configuration for Axon MCP Server.

This module configures the Celery app for distributed task processing
including repository synchronization, parsing, extraction, and embedding generation.
"""

from celery import Celery, signals
from src.config.settings import settings

# Initialize Celery app
celery_app = Celery(
    'axon_mcp_server',
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend
)

# Configure Celery
celery_app.conf.update(
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # Timezone
    timezone='UTC',
    enable_utc=True,
    
    # Task tracking
    task_track_started=True,
    task_send_sent_event=True,
    
    # Time limits
    task_time_limit=settings.celery_task_time_limit,
    task_soft_time_limit=settings.celery_task_soft_time_limit,
    
    # Worker settings
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    
    # Task routing
    task_routes={
        'src.workers.tasks.sync_repository': {'queue': 'repository_sync'},
        'src.workers.tasks.parse_file_task': {'queue': 'file_parsing'},
        'src.workers.tasks.generate_embeddings_task': {'queue': 'embeddings'},
        'src.workers.enrichment_worker.enrich_batch': {'queue': 'ai_enrichment'},
        'src.workers.aggregation_worker.aggregate_repository_summary': {'queue': 'repository_aggregation'},
    },
    
    # Default queue settings
    task_default_queue='default',
    task_default_exchange='default',
    task_default_exchange_type='direct',
    task_default_routing_key='default',
    
    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    result_persistent=True,
    
    # Retry settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Connection settings
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
)

from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    "refresh-system-context-every-hour": {
        "task": "src.workers.system_context_worker.generate_context",
        "schedule": crontab(minute=0),  # Every hour
        "args": (None,),
    },
}

# Auto-discover tasks
celery_app.autodiscover_tasks(['src.workers'])


@signals.worker_process_init.connect
def setup_worker_credentials(**kwargs):
    """
    Setup git credentials when worker process starts.
    
    This ensures credentials are configured in each worker process
    before any git operations are performed.
    """
    try:
        from src.azuredevops.repository_manager import setup_git_credentials
        setup_git_credentials()
    except Exception as exc:
        # Use Celery's logger if available, otherwise import
        try:
            from celery.utils.log import get_logger
            logger = get_logger(__name__)
            logger.warning(f"Worker git credentials setup failed: {exc}")
        except ImportError:
            pass  # Silently fail if logging not available 


