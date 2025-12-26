"""Redis caching layer for search results and queries."""

import json
import hashlib
from typing import Any, Optional, Callable
from functools import wraps
from datetime import timedelta

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

from src.utils.logging_config import get_logger
from src.config.settings import settings

logger = get_logger(__name__)


class RedisCache:
    """Redis-based caching layer."""
    
    def __init__(self, redis_url: Optional[str] = None, default_ttl: int = 300):
        """
        Initialize Redis cache.
        
        Args:
            redis_url: Redis connection URL (uses settings if not provided)
            default_ttl: Default TTL in seconds (5 minutes)
        """
        self.redis_url = redis_url or settings.redis_url
        self.default_ttl = default_ttl
        self._client: Optional[redis.Redis] = None
        # Check if Redis is enabled in settings and if the library is available
        self._enabled = settings.redis_cache_enabled and redis is not None
        
        if not settings.redis_cache_enabled:
            logger.info("redis_cache_disabled", message="Redis caching disabled via configuration")
        elif not redis:
            logger.warning("redis_not_installed", message="Redis library not installed, caching disabled")
    
    async def connect(self):
        """Establish Redis connection."""
        if not self._enabled:
            return
        
        try:
            self._client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            await self._client.ping()
            logger.info("redis_connected", url=self.redis_url)
        except Exception as e:
            # Log as warning since Redis is optional - app will continue without caching
            logger.warning("redis_connection_failed", error=str(e), message="Redis caching disabled, application will continue without cache")
            self._enabled = False
            self._client = None
    
    async def disconnect(self):
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            logger.info("redis_disconnected")
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        if not self._enabled or not self._client:
            return None
        
        try:
            value = await self._client.get(key)
            if value:
                logger.debug("cache_hit", key=key)
                return json.loads(value)
            else:
                logger.debug("cache_miss", key=key)
                return None
        except Exception as e:
            logger.error("cache_get_failed", key=key, error=str(e))
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (uses default if not specified)
        """
        if not self._enabled or not self._client:
            return
        
        try:
            ttl = ttl or self.default_ttl
            serialized = json.dumps(value)
            await self._client.setex(key, ttl, serialized)
            logger.debug("cache_set", key=key, ttl=ttl)
        except Exception as e:
            logger.error("cache_set_failed", key=key, error=str(e))
    
    async def delete(self, key: str):
        """Delete key from cache."""
        if not self._enabled or not self._client:
            return
        
        try:
            await self._client.delete(key)
            logger.debug("cache_delete", key=key)
        except Exception as e:
            logger.error("cache_delete_failed", key=key, error=str(e))
    
    async def delete_pattern(self, pattern: str):
        """
        Delete all keys matching pattern.
        
        Args:
            pattern: Pattern to match (e.g., "search:*")
        """
        if not self._enabled or not self._client:
            return
        
        try:
            cursor = 0
            count = 0
            while True:
                cursor, keys = await self._client.scan(cursor, match=pattern, count=100)
                if keys:
                    await self._client.delete(*keys)
                    count += len(keys)
                if cursor == 0:
                    break
            logger.info("cache_pattern_deleted", pattern=pattern, count=count)
        except Exception as e:
            logger.error("cache_pattern_delete_failed", pattern=pattern, error=str(e))
    
    def generate_key(self, prefix: str, *args, **kwargs) -> str:
        """
        Generate cache key from arguments.
        
        Args:
            prefix: Key prefix
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Generated cache key
        """
        # Create deterministic key from arguments
        key_parts = [prefix]
        
        # Add positional args
        for arg in args:
            key_parts.append(str(arg))
        
        # Add keyword args (sorted for consistency)
        for k in sorted(kwargs.keys()):
            key_parts.append(f"{k}={kwargs[k]}")
        
        # Hash if too long
        key = ":".join(key_parts)
        if len(key) > 200:
            key_hash = hashlib.md5(key.encode()).hexdigest()
            key = f"{prefix}:{key_hash}"
        
        return key


def cache(ttl: int = 300, key_prefix: Optional[str] = None):
    """
    Decorator for caching function results.
    
    Args:
        ttl: Time to live in seconds
        key_prefix: Optional key prefix (uses function name if not provided)
        
    Example:
        @cache(ttl=300, key_prefix="search")
        async def search_code(query: str, limit: int = 10):
            # ... expensive operation ...
            return results
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get cache instance (assuming it's passed as dependency or global)
            cache_instance = kwargs.pop('cache', None)
            
            if not cache_instance or not cache_instance._enabled:
                # No cache, execute function directly
                return await func(*args, **kwargs)
            
            # Generate cache key
            prefix = key_prefix or func.__name__
            cache_key = cache_instance.generate_key(prefix, *args, **kwargs)
            
            # Try to get from cache
            cached_result = await cache_instance.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Store in cache
            await cache_instance.set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator


# Global cache instance
_global_cache: Optional[RedisCache] = None


async def get_cache() -> RedisCache:
    """Get or create global cache instance."""
    global _global_cache
    
    if _global_cache is None:
        _global_cache = RedisCache()
        await _global_cache.connect()
    
    return _global_cache


async def invalidate_search_cache():
    """Invalidate all search-related cache entries."""
    cache = await get_cache()
    await cache.delete_pattern("search:*")
    await cache.delete_pattern("query:*")


async def invalidate_repository_cache(repository_id: int):
    """
    Invalidate all cache entries for a repository.
    
    Args:
        repository_id: Repository ID
    """
    cache = await get_cache()
    await cache.delete_pattern(f"*:repo:{repository_id}:*")

