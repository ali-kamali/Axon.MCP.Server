# Celery Workers Module

## Overview

This module provides distributed task processing for the Axon MCP Server using Celery. Workers handle long-running operations asynchronously to keep the API responsive.

## Components

### 1. Celery App (`celery_app.py`)

Main Celery application configuration with task routing and worker settings.

```python
from src.workers.celery_app import celery_app

# Access the Celery app
celery_app.conf
```

### 2. Tasks (`tasks.py`)

Background tasks for repository processing:

```python
from src.workers.tasks import sync_repository, parse_file_task, generate_embeddings_task

# Queue a repository sync
sync_repository.delay(repository_id=123)

# Parse a file
parse_file_task.delay(file_id=456)

# Generate embeddings
generate_embeddings_task.delay(chunk_ids=[1, 2, 3])
```

### 3. Distributed Lock (`distributed_lock.py`)

Redis-based locking to prevent concurrent processing:

```python
from src.workers.distributed_lock import get_distributed_lock

lock = get_distributed_lock()
with lock.acquire("resource-key", timeout=300) as acquired:
    if acquired:
        # Process resource
        pass
```

### 4. Job Monitor (`job_monitor.py`)

Monitor and manage background jobs:

```python
from src.workers.job_monitor import JobMonitor
from src.database.session import get_async_session

async with get_async_session() as session:
    monitor = JobMonitor(session)
    
    # Get running jobs
    jobs = await monitor.get_running_jobs()
    
    # Get stuck jobs
    stuck = await monitor.get_stuck_jobs(timeout_minutes=60)
    
    # Retry failed job
    await monitor.retry_failed_job(job_id=123)
```

## Task Queues

- **default**: General purpose tasks
- **repository_sync**: Repository synchronization
- **file_parsing**: Individual file parsing
- **embeddings**: Embedding generation

## Starting Workers

### Development

```bash
python scripts/start_celery_worker.py --loglevel debug
```

### Production

```bash
# Repository sync worker
python scripts/start_celery_worker.py \
    --queue repository_sync \
    --concurrency 4 \
    --loglevel info

# Embeddings worker
python scripts/start_celery_worker.py \
    --queue embeddings \
    --concurrency 2 \
    --loglevel info
```

## Monitoring

```bash
# Worker status
python scripts/celery_monitor.py status

# Job statistics
python scripts/celery_monitor.py jobs

# Find stuck jobs
python scripts/celery_monitor.py stuck --fix

# List failed jobs
python scripts/celery_monitor.py failed

# Retry a job
python scripts/celery_monitor.py retry 123
```

## Task Flow

### Repository Sync Pipeline

1. **Acquire Lock**: Prevent concurrent processing
2. **Clone Repository**: Git clone or update
3. **Parse Files**: Extract symbols from code
4. **Extract Knowledge**: Build relationships
5. **Generate Embeddings**: Create vector embeddings
6. **Update Status**: Mark as completed

### Error Handling

- Automatic retries (up to 3 attempts)
- Exponential backoff (60s, 120s, 240s)
- Graceful error logging
- Database rollback on failure

## Configuration

### Environment Variables

```bash
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
CELERY_TASK_TIME_LIMIT=3600
CELERY_TASK_SOFT_TIME_LIMIT=3000
```

### Worker Settings

Modify `celery_app.py`:

```python
celery_app.conf.update(
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    task_time_limit=3600,
)
```

## Testing

```bash
# Run unit tests
pytest tests/unit/test_celery_tasks.py
pytest tests/unit/test_distributed_lock.py
pytest tests/unit/test_job_monitor.py

# Run integration tests
pytest tests/integration/test_worker_pipeline.py -m integration
```

## Performance Tips

1. **Concurrency**: Adjust based on workload
   - I/O-bound: Higher concurrency (8+)
   - CPU-bound: Lower concurrency (2-4)

2. **Memory**: Limit tasks per child to prevent leaks
   ```python
   worker_max_tasks_per_child=1000
   ```

3. **Queues**: Separate workers for different queues
   ```bash
   # Heavy tasks
   celery worker --queue repository_sync --concurrency 2
   
   # Light tasks
   celery worker --queue embeddings --concurrency 4
   ```

## Troubleshooting

### Workers not starting
- Check Redis connection
- Verify database connection
- Review logs with `--loglevel debug`

### Tasks not processing
- Verify workers are running
- Check queue names match
- Ensure correct permissions

### High memory usage
- Reduce concurrency
- Lower `worker_max_tasks_per_child`
- Monitor with Flower

## Documentation

- [Complete Guide](../../docs/CELERY_WORKERS_GUIDE.md)
- [Implementation Summary](../../docs/TASK_09_IMPLEMENTATION_SUMMARY.md)
- [Task Specification](../../docs/TASK_09_Celery_Workers.md)

## API Reference

See module docstrings for detailed API documentation:

```python
help(sync_repository)
help(DistributedLock)
help(JobMonitor)
```

