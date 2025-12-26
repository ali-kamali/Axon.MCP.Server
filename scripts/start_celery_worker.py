#!/usr/bin/env python3
"""
Start Celery worker for Axon MCP Server.

This script starts a Celery worker with the appropriate configuration
for processing repository synchronization tasks.

Usage:
    python scripts/start_celery_worker.py [OPTIONS]

Options:
    --queue QUEUE       Specify queue to process (default, repository_sync, embeddings)
    --concurrency N     Number of concurrent workers (default: 4)
    --loglevel LEVEL    Log level (debug, info, warning, error)
    --beat              Start with beat scheduler
"""

import sys
import argparse
import asyncio
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.workers.celery_app import celery_app


def run_auto_migrations():
    """Run auto-migrations before starting worker."""
    try:
        from scripts.auto_migrate import run_all_migrations
        print("Running auto-migrations...")
        success = asyncio.run(run_all_migrations())
        if success:
            print("✓ Auto-migrations completed successfully")
        else:
            print("⚠ Auto-migrations failed, but worker will continue")
    except Exception as e:
        print(f"⚠ Auto-migrations error: {e}, but worker will continue")


def main():
    """Start Celery worker."""
    parser = argparse.ArgumentParser(
        description="Start Celery worker for Axon MCP Server"
    )
    parser.add_argument(
        '--queue',
        default='default,repository_sync,file_parsing,embeddings',
        help='Queue(s) to process (comma-separated)'
    )
    parser.add_argument(
        '--concurrency',
        type=int,
        default=4,
        help='Number of concurrent workers'
    )
    parser.add_argument(
        '--loglevel',
        default='info',
        choices=['debug', 'info', 'warning', 'error'],
        help='Log level'
    )
    parser.add_argument(
        '--beat',
        action='store_true',
        help='Start with beat scheduler'
    )
    parser.add_argument(
        '--pool',
        default='prefork',
        choices=['prefork', 'solo', 'eventlet', 'gevent'],
        help='Worker pool type'
    )
    
    args = parser.parse_args()
    
    # Run auto-migrations before starting worker
    run_auto_migrations()
    
    # Build worker arguments
    worker_args = [
        'worker',
        f'--loglevel={args.loglevel}',
        f'--concurrency={args.concurrency}',
        f'--queues={args.queue}',
        f'--pool={args.pool}',
    ]
    
    if args.beat:
        worker_args.append('--beat')
    
    print(f"Starting Celery worker with args: {' '.join(worker_args)}")
    print(f"Processing queues: {args.queue}")
    print(f"Concurrency: {args.concurrency}")
    print(f"Pool: {args.pool}")
    print(f"Log level: {args.loglevel}")
    
    # Start worker
    celery_app.worker_main(argv=worker_args)


if __name__ == '__main__':
    main()

