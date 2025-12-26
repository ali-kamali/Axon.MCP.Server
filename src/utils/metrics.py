from functools import wraps
from time import time
from typing import Any, Callable

import asyncio
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, Info  # noqa: F401


# Repository Metrics
repository_sync_total = Counter(
    "repository_sync_total", "Total number of repository syncs", ["status"]
)

repository_sync_duration = Histogram(
    "repository_sync_duration_seconds", "Repository sync duration", ["repository_name"]
)

# Parsing Metrics
parsing_duration = Histogram(
    "parsing_duration_seconds", "File parsing duration", ["language"]
)

parsing_errors_total = Counter(
    "parsing_errors_total", "Total parsing errors", ["language", "error_type"]
)

files_parsed_total = Counter(
    "files_parsed_total", "Total files parsed", ["language", "status"]
)

# Embedding Metrics
embedding_generation_duration = Histogram(
    "embedding_generation_duration_seconds", "Embedding generation duration", ["model"]
)

embeddings_generated_total = Counter(
    "embeddings_generated_total", "Total embeddings generated", ["model", "status"]
)

# Search Metrics
search_duration = Histogram(
    "search_duration_seconds", "Search query duration", ["search_type"]
)

search_queries_total = Counter(
    "search_queries_total", "Total search queries", ["search_type", "status"]
)

search_results_count = Histogram(
    "search_results_count", "Number of search results returned", ["search_type"]
)

# Worker Metrics
active_workers = Gauge("active_workers", "Number of active Celery workers")

celery_tasks_total = Counter(
    "celery_tasks_total", "Total Celery tasks", ["task_name", "status"]
)

celery_task_duration = Histogram(
    "celery_task_duration_seconds", "Celery task duration", ["task_name"]
)

# API Metrics
api_requests_total = Counter(
    "api_requests_total", "Total API requests", ["method", "endpoint", "status"]
)

api_request_duration = Histogram(
    "api_request_duration_seconds", "API request duration", ["method", "endpoint"]
)

# MCP Metrics
mcp_tool_calls_total = Counter(
    "mcp_tool_calls_total", "Total MCP tool calls", ["tool_name", "status"]
)

mcp_tool_duration = Histogram(
    "mcp_tool_duration_seconds", "MCP tool execution duration", ["tool_name"]
)

# Database Metrics
db_query_duration = Histogram(
    "db_query_duration_seconds", "Database query duration", ["operation"]
)

db_connections_active = Gauge("db_connections_active", "Active database connections")

# System Metrics
memory_usage_bytes = Gauge("memory_usage_bytes", "Memory usage in bytes")

cpu_usage_percent = Gauge("cpu_usage_percent", "CPU usage percentage")


# Roslyn Metrics
roslyn_uptime_seconds = Gauge("roslyn_process_uptime_seconds", "Roslyn Analyzer uptime")
roslyn_failures_total = Counter("roslyn_failures_total", "Total Roslyn process failures")
roslyn_requests_total = Counter("roslyn_requests_total", "Total Roslyn requests", ["operation"])
roslyn_memory_mb = Gauge("roslyn_memory_mb", "Roslyn process memory usage in MB")


def track_time(metric: Histogram, labels: dict | None = None) -> Callable:
    """
    Decorator to track execution time of functions.

    Usage:
        @track_time(parsing_duration, {"language": "python"})
        async def parse_file():
            pass
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            start = time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time() - start
                if labels:
                    metric.labels(**labels).observe(duration)
                else:
                    metric.observe(duration)

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            start = time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time() - start
                if labels:
                    metric.labels(**labels).observe(duration)
                else:
                    metric.observe(duration)

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def increment_counter(counter: Counter, labels: dict | None = None) -> Callable:
    """
    Decorator to increment counter on function call.

    Usage:
        @increment_counter(api_requests_total, {"method": "GET", "endpoint": "/search", "status": "200"})
        async def search():
            pass
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            try:
                result = await func(*args, **kwargs)
                if labels:
                    counter.labels(**labels).inc()
                else:
                    counter.inc()
                return result
            except Exception:
                error_labels = labels.copy() if labels else {}
                if "status" in error_labels:
                    error_labels["status"] = "error"
                counter.labels(**error_labels).inc()
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            try:
                result = func(*args, **kwargs)
                if labels:
                    counter.labels(**labels).inc()
                else:
                    counter.inc()
                return result
            except Exception:
                error_labels = labels.copy() if labels else {}
                if "status" in error_labels:
                    error_labels["status"] = "error"
                counter.labels(**error_labels).inc()
                raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


