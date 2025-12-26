import asyncio

import psutil
from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from src.config.settings import settings
from src.utils.metrics import cpu_usage_percent, memory_usage_bytes


router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }


@router.get("/health/ready")
async def readiness_check() -> dict[str, str]:
    """
    Readiness probe for Kubernetes.
    Checks if service is ready to accept traffic.
    """
    return {"status": "ready"}


@router.get("/health/live")
async def liveness_check() -> dict[str, str]:
    """
    Liveness probe for Kubernetes.
    Checks if service is alive (not deadlocked).
    """
    return {"status": "alive"}


@router.get("/metrics")
async def metrics() -> Response:
    """
    Prometheus metrics endpoint.
    Exposes all application metrics.
    """
    memory_usage_bytes.set(psutil.Process().memory_info().rss)
    cpu_usage_percent.set(psutil.cpu_percent())

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


