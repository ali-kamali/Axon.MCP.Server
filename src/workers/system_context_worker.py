"""
Celery worker for system context generation.
"""
import asyncio
from typing import Optional
from celery import shared_task

from src.workers.celery_app import celery_app
from src.workers.utils import _run_with_engine_cleanup
from src.database.session import AsyncSessionLocal
from src.utils.logging_config import get_logger
from src.utils.system_context_generator import SystemContextGenerator
from src.utils.redis_cache import get_cache
from src.workers.distributed_lock import get_distributed_lock

logger = get_logger(__name__)

SYSTEM_CONTEXT_CACHE_KEY = "system_context_map"
SYSTEM_CONTEXT_TTL = 3600 * 24  # 24 hours

@celery_app.task(bind=True, name="src.workers.system_context_worker.generate_context", max_retries=3)
def generate_context(self, repository_id: Optional[int] = None, blocking_timeout: int = 5):
    """
    Generate and cache system context.
    
    Args:
        repository_id: Repository to process
        blocking_timeout: How long to wait for lock (default 5s for scheduled tasks, use higher for manual)
    """
    try:
        return asyncio.run(_run_with_engine_cleanup(_generate_context_async(repository_id, blocking_timeout)))
    except Exception as e:
        logger.error(f"System context generation failed: {e}")
        raise self.retry(exc=e, countdown=300)

async def _generate_context_async(repository_id: Optional[int] = None, blocking_timeout: int = 5):
    """Async implementation of context generation."""
    lock_key = f"system_context_gen:{repository_id or 'global'}"
    lock = get_distributed_lock()
    
    # Use distributed lock to prevent concurrent generation
    with lock.acquire(lock_key, timeout=600, blocking_timeout=blocking_timeout) as acquired:
        if not acquired:
            logger.info("system_context_generation_skipped_locked", repository_id=repository_id or "global")
            return {"status": "skipped", "reason": "already_running"}
            
        logger.info("system_context_generation_started", repository_id=repository_id or "global")
        
        try:
            async with AsyncSessionLocal() as session:
                generator = SystemContextGenerator(session)
                context = await generator.generate_system_map(repository_id)
                
                # Cache the result
                try:
                    cache = await get_cache()
                    key = f"{SYSTEM_CONTEXT_CACHE_KEY}:{repository_id}" if repository_id else SYSTEM_CONTEXT_CACHE_KEY
                    await cache.set(key, context, ttl=SYSTEM_CONTEXT_TTL)
                    logger.info("system_context_generated_and_cached", key=key)
                except Exception as e:
                    logger.error(f"Failed to cache system context: {e}")
                    # Continue - generation succeeded even if cache failed
                
            return {"status": "completed", "key": context.get("generated_at", "unknown")}
            
        except Exception as e:
            logger.error(f"System context generation failed inside lock: {e}")
            raise
