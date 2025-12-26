"""
Distributed locking mechanism using Redis for Celery workers.

This module provides Redis-based distributed locking to prevent
concurrent processing of the same resources across multiple workers.
"""

import redis
import threading
from contextlib import contextmanager
from typing import Optional
from src.config.settings import settings
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class DistributedLock:
    """Redis-based distributed locking for workers."""
    
    def __init__(self):
        """Initialize Redis client for locking."""
        try:
            self.redis_client = redis.from_url(
                settings.redis_url,
                max_connections=settings.redis_max_connections,
                decode_responses=True
            )
            # Test connection
            self.redis_client.ping()
            logger.info("distributed_lock_initialized")
        except Exception as e:
            logger.error("distributed_lock_init_failed", error=str(e))
            self.redis_client = None
    
    @contextmanager
    def acquire(
        self,
        resource: str,
        timeout: int = 300,
        blocking_timeout: Optional[int] = None
    ):
        """
        Acquire lock for resource.
        
        Args:
            resource: Resource identifier (e.g., "repo:123")
            timeout: Lock expiration timeout in seconds (default: 300)
            blocking_timeout: How long to wait for lock acquisition (default: None, don't wait)
            
        Yields:
            bool: True if lock acquired, False otherwise
            
        Example:
            >>> lock = DistributedLock()
            >>> with lock.acquire("repo:123", timeout=600) as acquired:
            ...     if acquired:
            ...         # Process repository
            ...         pass
            ...     else:
            ...         # Lock not acquired, skip processing
            ...         pass
        """
        if not self.redis_client:
            # No Redis, proceed without locking (not recommended for production)
            logger.warning(
                "distributed_lock_unavailable_proceeding_without_lock",
                resource=resource
            )
            yield True
            return
        
        lock_key = f"lock:{resource}"
        lock_acquired = False
        
        try:
            # Try to acquire lock
            lock_acquired = self.redis_client.set(
                lock_key,
                "locked",
                nx=True,  # Only set if not exists
                ex=timeout  # Expiration time
            )
            
            if lock_acquired:
                logger.debug("lock_acquired", resource=resource, timeout=timeout)
            else:
                logger.warning(
                    "lock_not_acquired",
                    resource=resource,
                    message="Resource is currently locked by another worker"
                )
            
            # Always yield the result, even if False
            yield lock_acquired
                
        except Exception as e:
            logger.error(
                "lock_acquisition_error",
                resource=resource,
                error=str(e)
            )
            # Re-raise the exception instead of yielding True
            raise
            
        finally:
            if lock_acquired:
                try:
                    # Release lock
                    self.redis_client.delete(lock_key)
                    logger.debug("lock_released", resource=resource)
                except Exception as e:
                    logger.error(
                        "lock_release_error",
                        resource=resource,
                        error=str(e)
                    )
    
    def is_locked(self, resource: str) -> bool:
        """
        Check if resource is currently locked.
        
        Args:
            resource: Resource identifier
            
        Returns:
            bool: True if locked, False otherwise
        """
        if not self.redis_client:
            return False
        
        lock_key = f"lock:{resource}"
        try:
            return self.redis_client.exists(lock_key) > 0
        except Exception as e:
            logger.error("lock_check_error", resource=resource, error=str(e))
            return False
    
    def extend_lock(self, resource: str, additional_time: int) -> bool:
        """
        Extend lock expiration time.
        
        Args:
            resource: Resource identifier
            additional_time: Additional time in seconds
            
        Returns:
            bool: True if extended successfully
        """
        if not self.redis_client:
            return False
        
        lock_key = f"lock:{resource}"
        try:
            ttl = self.redis_client.ttl(lock_key)
            if ttl > 0:
                self.redis_client.expire(lock_key, ttl + additional_time)
                logger.debug(
                    "lock_extended",
                    resource=resource,
                    additional_time=additional_time
                )
                return True
            return False
        except Exception as e:
            logger.error("lock_extend_error", resource=resource, error=str(e))
            return False


# Global instance with thread-safe initialization
_lock_instance: Optional[DistributedLock] = None
_lock_init_lock = threading.Lock()


def get_distributed_lock() -> DistributedLock:
    """
    Get global distributed lock instance (singleton pattern).
    Thread-safe initialization using double-checked locking.
    
    Returns:
        DistributedLock: Global lock instance
    """
    global _lock_instance
    
    # First check (without lock) for performance
    if _lock_instance is None:
        # Acquire lock for initialization
        with _lock_init_lock:
            # Double-check inside lock to prevent race condition
            if _lock_instance is None:
                _lock_instance = DistributedLock()
                logger.info("distributed_lock_singleton_initialized")
    
    return _lock_instance