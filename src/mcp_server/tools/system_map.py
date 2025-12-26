from typing import List, Optional
from mcp.server.fastmcp import Context

from src.workers.system_context_worker import SYSTEM_CONTEXT_CACHE_KEY, generate_context
from src.utils.redis_cache import get_cache

async def get_system_map(ctx: Context, repository_id: int = 0) -> str:
    """
    Get a high-level map of the system or a specific repository.
    
    Args:
        repository_id: Optional ID to get specific repo maps. 0 for global.
    """
    key = f"{SYSTEM_CONTEXT_CACHE_KEY}:{repository_id}" if repository_id else SYSTEM_CONTEXT_CACHE_KEY
    
    # Try cache first
    cache = await get_cache()
    cached = await cache.get(key)
    if cached:
        return str(cached)
        
    # If not cached, trigger generation (this might take a while, so we return a message)
    # Ideally, we should wait, but for now let's just trigger
    generate_context.delay(repository_id if repository_id > 0 else None, blocking_timeout=60)
    
    return "System map is being generated. Please try again in a few seconds."
