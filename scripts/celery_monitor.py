#!/usr/bin/env python3
"""
Monitor Celery workers and jobs.

This script provides a simple CLI to monitor Celery workers,
view job statuses, and manage stuck/failed jobs.

Usage:
    python scripts/celery_monitor.py [COMMAND]

Commands:
    status      Show worker status
    jobs        Show job statistics
    stuck       Find and fix stuck jobs
    failed      List failed jobs
    retry       Retry a failed job
"""

import sys
import asyncio
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.workers.celery_app import celery_app
from src.workers.job_monitor import JobMonitor
from src.database.session import get_async_session


async def show_worker_status():
    """Show status of all Celery workers."""
    inspector = celery_app.control.inspect()
    
    print("\n=== Worker Status ===\n")
    
    # Active workers
    active = inspector.active()
    if active:
        print("Active Workers:")
        for worker, tasks in active.items():
            print(f"  {worker}: {len(tasks)} active tasks")
            for task in tasks[:3]:  # Show first 3
                print(f"    - {task['name']} ({task['id'][:8]}...)")
    else:
        print("No active workers")
    
    # Registered workers
    stats = inspector.stats()
    if stats:
        print("\nRegistered Workers:")
        for worker, stat in stats.items():
            print(f"  {worker}")
            print(f"    Pool: {stat.get('pool', {}).get('implementation', 'unknown')}")
            print(f"    Max concurrency: {stat.get('pool', {}).get('max-concurrency', 'N/A')}")
    
    print()


async def show_job_stats():
    """Show job statistics."""
    async with get_async_session() as session:
        monitor = JobMonitor(session)
        
        print("\n=== Job Statistics ===\n")
        
        stats = await monitor.get_job_stats()
        print(f"Total jobs: {stats['total']}")
        print(f"Pending: {stats['pending']}")
        print(f"Running: {stats['running']}")
        print(f"Completed: {stats['completed']}")
        print(f"Failed: {stats['failed']}")
        print(f"Cancelled: {stats['cancelled']}")
        
        # Show running jobs
        running_jobs = await monitor.get_running_jobs()
        if running_jobs:
            print("\nCurrently Running:")
            for job in running_jobs[:5]:
                elapsed = (
                    asyncio.get_event_loop().time() - job.started_at.timestamp()
                    if job.started_at else 0
                )
                print(f"  Job {job.id}: {job.job_type} (elapsed: {elapsed:.0f}s)")
        
        print()


async def find_stuck_jobs(fix=False):
    """Find and optionally fix stuck jobs."""
    async with get_async_session() as session:
        monitor = JobMonitor(session)
        
        print("\n=== Stuck Jobs ===\n")
        
        stuck_jobs = await monitor.get_stuck_jobs(timeout_minutes=60)
        
        if not stuck_jobs:
            print("No stuck jobs found")
            print()
            return
        
        print(f"Found {len(stuck_jobs)} stuck job(s):")
        for job in stuck_jobs:
            elapsed = (
                asyncio.get_event_loop().time() - job.started_at.timestamp()
                if job.started_at else 0
            )
            print(f"  Job {job.id}: {job.job_type}")
            print(f"    Started: {job.started_at}")
            print(f"    Elapsed: {elapsed:.0f} seconds")
        
        if fix:
            print("\nMarking stuck jobs as failed...")
            for job in stuck_jobs:
                await monitor.mark_job_as_stuck(job.id)
                print(f"  Marked job {job.id} as failed")
        
        print()


async def list_failed_jobs():
    """List recent failed jobs."""
    async with get_async_session() as session:
        monitor = JobMonitor(session)
        
        print("\n=== Failed Jobs ===\n")
        
        failed_jobs = await monitor.get_failed_jobs(limit=10)
        
        if not failed_jobs:
            print("No failed jobs found")
            print()
            return
        
        print(f"Recent failed jobs (showing up to 10):")
        for job in failed_jobs:
            print(f"\nJob {job.id}:")
            print(f"  Type: {job.job_type}")
            print(f"  Repository: {job.repository_id}")
            print(f"  Failed at: {job.completed_at}")
            print(f"  Retry count: {job.retry_count}/{job.max_retries}")
            if job.error_message:
                error_preview = job.error_message[:100]
                print(f"  Error: {error_preview}...")
        
        print()


async def retry_job(job_id: int):
    """Retry a failed job."""
    async with get_async_session() as session:
        monitor = JobMonitor(session)
        
        print(f"\n=== Retrying Job {job_id} ===\n")
        
        success = await monitor.retry_failed_job(job_id)
        
        if success:
            print(f"Successfully queued job {job_id} for retry")
        else:
            print(f"Failed to retry job {job_id}")
            print("Possible reasons:")
            print("  - Job not found")
            print("  - Job is not in failed state")
            print("  - Max retries exceeded")
        
        print()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == 'status':
        asyncio.run(show_worker_status())
    elif command == 'jobs':
        asyncio.run(show_job_stats())
    elif command == 'stuck':
        fix = '--fix' in sys.argv
        asyncio.run(find_stuck_jobs(fix=fix))
    elif command == 'failed':
        asyncio.run(list_failed_jobs())
    elif command == 'retry':
        if len(sys.argv) < 3:
            print("Usage: celery_monitor.py retry JOB_ID")
            sys.exit(1)
        job_id = int(sys.argv[2])
        asyncio.run(retry_job(job_id))
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()