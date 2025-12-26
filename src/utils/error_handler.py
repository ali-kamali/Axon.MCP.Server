"""Centralized error handling and recovery."""

import traceback
from typing import Callable, Any, Optional
from functools import wraps
from datetime import datetime

from src.utils.logging_config import get_logger
from src.utils.metrics import error_counter, error_by_type_counter

logger = get_logger(__name__)


class RetryableError(Exception):
    """Error that should trigger a retry."""
    pass


class FatalError(Exception):
    """Error that should not be retried."""
    pass


def handle_errors(
    operation_name: str,
    reraise: bool = True,
    default_return: Any = None,
    log_traceback: bool = True
):
    """
    Decorator for centralized error handling.
    
    Args:
        operation_name: Name of the operation for logging
        reraise: Whether to re-raise the exception
        default_return: Value to return on error if not reraising
        log_traceback: Whether to log full traceback
        
    Example:
        @handle_errors("parse_file", reraise=False, default_return=[])
        def parse_file(path: str):
            # ... parsing logic ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                return await _handle_exception(
                    e, operation_name, func.__name__,
                    log_traceback, reraise, default_return
                )
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                return _handle_exception_sync(
                    e, operation_name, func.__name__,
                    log_traceback, reraise, default_return
                )
        
        # Return appropriate wrapper based on function type
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


async def _handle_exception(
    error: Exception,
    operation: str,
    function_name: str,
    log_traceback: bool,
    reraise: bool,
    default_return: Any
):
    """Handle exception asynchronously."""
    # Increment error metrics
    error_counter.inc()
    error_by_type_counter.labels(error_type=type(error).__name__).inc()
    
    # Log error
    error_data = {
        "operation": operation,
        "function": function_name,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if log_traceback:
        error_data["traceback"] = traceback.format_exc()
    
    logger.error("operation_failed", **error_data)
    
    # Store error for monitoring
    await _store_error_for_monitoring(error_data)
    
    if reraise:
        raise
    
    return default_return


def _handle_exception_sync(
    error: Exception,
    operation: str,
    function_name: str,
    log_traceback: bool,
    reraise: bool,
    default_return: Any
):
    """Handle exception synchronously."""
    # Increment error metrics
    error_counter.inc()
    error_by_type_counter.labels(error_type=type(error).__name__).inc()
    
    # Log error
    error_data = {
        "operation": operation,
        "function": function_name,
        "error_type": type(error).__name__,
        "error_message": str(error)
    }
    
    if log_traceback:
        error_data["traceback"] = traceback.format_exc()
    
    logger.error("operation_failed", **error_data)
    
    if reraise:
        raise
    
    return default_return


async def _store_error_for_monitoring(error_data: dict):
    """Store error in database or monitoring system."""
    # This could write to a database table, send to Sentry, etc.
    pass


def retry_on_failure(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Decorator for retrying operations on failure.
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay on each retry
        
    Example:
        @retry_on_failure(max_retries=3, delay=1.0, backoff=2.0)
        async def unreliable_operation():
            # ... might fail occasionally ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            import asyncio
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except RetryableError as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            "retrying_operation",
                            function=func.__name__,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            delay=current_delay
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            "max_retries_exceeded",
                            function=func.__name__,
                            attempts=max_retries + 1
                        )
                except FatalError as e:
                    logger.error("fatal_error_no_retry", function=func.__name__, error=str(e))
                    raise
                except Exception as e:
                    # Treat unknown exceptions as retryable
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            "retrying_operation_unknown_error",
                            function=func.__name__,
                            attempt=attempt + 1,
                            error=str(e)
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
            
            raise last_exception
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            import time
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (RetryableError, Exception) as e:
                    last_exception = e
                    if attempt < max_retries and not isinstance(e, FatalError):
                        time.sleep(current_delay)
                        current_delay *= backoff
                    elif isinstance(e, FatalError):
                        raise
            
            raise last_exception
        
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


class ErrorRecovery:
    """Handles error recovery strategies."""
    
    @staticmethod
    async def recover_from_database_error(error: Exception, operation: str) -> bool:
        """
        Attempt to recover from database error.
        
        Returns:
            True if recovery successful, False otherwise
        """
        logger.warning("attempting_database_recovery", operation=operation, error=str(error))
        
        # Attempt to reconnect
        try:
            from src.database.connection_pool import get_connection_pool
            pool = await get_connection_pool()
            
            # Check health
            if await pool.health_check():
                logger.info("database_recovery_successful")
                return True
            else:
                # Try to reinitialize
                await pool.dispose()
                await pool.initialize()
                
                if await pool.health_check():
                    logger.info("database_reconnection_successful")
                    return True
        except Exception as e:
            logger.error("database_recovery_failed", error=str(e))
        
        return False
    
    @staticmethod
    async def recover_from_cache_error(error: Exception) -> bool:
        """
        Attempt to recover from cache error.
        
        Returns:
            True if recovery successful, False otherwise
        """
        logger.warning("cache_error_recovery", error=str(error))
        
        # Cache errors are non-fatal, just disable caching
        try:
            from src.utils.redis_cache import get_cache
            cache = await get_cache()
            cache._enabled = False
            logger.warning("cache_disabled_due_to_errors")
            return True
        except Exception:
            return True  # Cache failure is acceptable

