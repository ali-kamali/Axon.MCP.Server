"""Quick script to check job status directly from database."""
import asyncio
import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Ensure we use localhost
db_url = os.getenv('DATABASE_URL')
if db_url and '@postgres:' in db_url:
    os.environ['DATABASE_URL'] = db_url.replace('@postgres:', '@localhost:')

from src.database.models import Job
from src.config.settings import settings

async def check_job(job_id: int):
    """Check the status of a specific job."""
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        result = await session.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()
        
        if job:
            print(f"\n{'='*60}")
            print(f"Job ID: {job.id}")
            print(f"Repository ID: {job.repository_id}")
            print(f"Job Type: {job.job_type}")
            print(f"Status: {job.status.value if hasattr(job.status, 'value') else job.status}")
            print(f"Started At: {job.started_at}")
            print(f"Completed At: {job.completed_at}")
            print(f"Duration: {job.duration_seconds}s")
            print(f"Celery Task ID: {job.celery_task_id}")
            if job.error_message:
                print(f"Error: {job.error_message}")
            print(f"{'='*60}\n")
        else:
            print(f"Job {job_id} not found!")
    
    await engine.dispose()

if __name__ == "__main__":
    import sys
    job_id = int(sys.argv[1]) if len(sys.argv) > 1 else 178
    asyncio.run(check_job(job_id))
