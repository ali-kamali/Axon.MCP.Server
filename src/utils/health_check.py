"""Health check system for monitoring service status."""

from typing import Dict, Optional
from datetime import datetime
from dataclasses import dataclass, asdict

from src.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ComponentHealth:
    """Health status of a component."""
    name: str
    status: str  # "healthy", "degraded", "unhealthy"
    message: Optional[str] = None
    response_time_ms: Optional[float] = None
    last_check: Optional[str] = None
    details: Optional[Dict] = None


class HealthCheck:
    """Comprehensive health check system."""
    
    def __init__(self):
        """Initialize health check system."""
        self.components = {}
    
    async def check_all(self) -> Dict[str, ComponentHealth]:
        """
        Check health of all system components.
        
        Returns:
            Dict of component names to their health status
        """
        results = {}
        
        # Check database
        results['database'] = await self._check_database()
        
        # Check Redis cache
        results['cache'] = await self._check_cache()
        
        # Check disk space
        results['disk'] = await self._check_disk_space()
        
        # Check memory
        results['memory'] = await self._check_memory()
        
        # Check workers (Celery)
        results['workers'] = await self._check_workers()
        
        return results
    
    async def get_overall_status(self) -> str:
        """
        Get overall system health status.
        
        Returns:
            "healthy", "degraded", or "unhealthy"
        """
        components = await self.check_all()
        
        # Count status types
        statuses = [c.status for c in components.values()]
        
        if all(s == "healthy" for s in statuses):
            return "healthy"
        elif any(s == "unhealthy" for s in statuses):
            return "unhealthy"
        else:
            return "degraded"
    
    async def _check_database(self) -> ComponentHealth:
        """Check database health."""
        import time
        start = time.time()
        
        try:
            from src.database.connection_pool import get_connection_pool
            pool = await get_connection_pool()
            
            # Check connection
            is_healthy = await pool.health_check()
            
            # Get pool status
            pool_status = await pool.get_pool_status()
            
            response_time = (time.time() - start) * 1000
            
            if is_healthy:
                return ComponentHealth(
                    name="database",
                    status="healthy",
                    message="Database connection successful",
                    response_time_ms=response_time,
                    last_check=datetime.utcnow().isoformat(),
                    details=pool_status
                )
            else:
                return ComponentHealth(
                    name="database",
                    status="unhealthy",
                    message="Database connection failed",
                    response_time_ms=response_time,
                    last_check=datetime.utcnow().isoformat()
                )
        except Exception as e:
            return ComponentHealth(
                name="database",
                status="unhealthy",
                message=f"Database error: {str(e)}",
                last_check=datetime.utcnow().isoformat()
            )
    
    async def _check_cache(self) -> ComponentHealth:
        """Check Redis cache health."""
        import time
        start = time.time()
        
        try:
            from src.utils.redis_cache import get_cache
            cache = await get_cache()
            
            if not cache._enabled:
                return ComponentHealth(
                    name="cache",
                    status="degraded",
                    message="Cache is disabled",
                    last_check=datetime.utcnow().isoformat()
                )
            
            # Try to set and get a test value
            test_key = "healthcheck:test"
            await cache.set(test_key, "test_value", ttl=10)
            value = await cache.get(test_key)
            await cache.delete(test_key)
            
            response_time = (time.time() - start) * 1000
            
            if value == "test_value":
                return ComponentHealth(
                    name="cache",
                    status="healthy",
                    message="Cache operational",
                    response_time_ms=response_time,
                    last_check=datetime.utcnow().isoformat()
                )
            else:
                return ComponentHealth(
                    name="cache",
                    status="degraded",
                    message="Cache read/write issue",
                    response_time_ms=response_time,
                    last_check=datetime.utcnow().isoformat()
                )
        except Exception as e:
            return ComponentHealth(
                name="cache",
                status="degraded",
                message=f"Cache error (non-fatal): {str(e)}",
                last_check=datetime.utcnow().isoformat()
            )
    
    async def _check_disk_space(self) -> ComponentHealth:
        """Check available disk space."""
        import shutil
        
        try:
            usage = shutil.disk_usage("/")
            percent_used = (usage.used / usage.total) * 100
            
            if percent_used < 80:
                status = "healthy"
                message = f"Disk usage: {percent_used:.1f}%"
            elif percent_used < 90:
                status = "degraded"
                message = f"Disk usage high: {percent_used:.1f}%"
            else:
                status = "unhealthy"
                message = f"Disk usage critical: {percent_used:.1f}%"
            
            return ComponentHealth(
                name="disk",
                status=status,
                message=message,
                last_check=datetime.utcnow().isoformat(),
                details={
                    "total_gb": usage.total / (1024**3),
                    "used_gb": usage.used / (1024**3),
                    "free_gb": usage.free / (1024**3),
                    "percent_used": percent_used
                }
            )
        except Exception as e:
            return ComponentHealth(
                name="disk",
                status="unhealthy",
                message=f"Disk check error: {str(e)}",
                last_check=datetime.utcnow().isoformat()
            )
    
    async def _check_memory(self) -> ComponentHealth:
        """Check memory usage."""
        import psutil
        
        try:
            memory = psutil.virtual_memory()
            percent_used = memory.percent
            
            if percent_used < 80:
                status = "healthy"
                message = f"Memory usage: {percent_used:.1f}%"
            elif percent_used < 90:
                status = "degraded"
                message = f"Memory usage high: {percent_used:.1f}%"
            else:
                status = "unhealthy"
                message = f"Memory usage critical: {percent_used:.1f}%"
            
            return ComponentHealth(
                name="memory",
                status=status,
                message=message,
                last_check=datetime.utcnow().isoformat(),
                details={
                    "total_gb": memory.total / (1024**3),
                    "available_gb": memory.available / (1024**3),
                    "used_gb": memory.used / (1024**3),
                    "percent": percent_used
                }
            )
        except Exception as e:
            return ComponentHealth(
                name="memory",
                status="unhealthy",
                message=f"Memory check error: {str(e)}",
                last_check=datetime.utcnow().isoformat()
            )
    
    async def _check_workers(self) -> ComponentHealth:
        """Check Celery workers status."""
        # This would check if Celery workers are running
        # Simplified implementation
        return ComponentHealth(
            name="workers",
            status="healthy",
            message="Worker check not implemented",
            last_check=datetime.utcnow().isoformat()
        )

