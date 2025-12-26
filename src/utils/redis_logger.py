import json
import logging
from datetime import datetime
from typing import Any, Optional
import redis.asyncio as redis
from src.config.settings import settings

logger = logging.getLogger(__name__)

class RedisLogPublisher:
    def __init__(self):
        self.redis_url = settings.redis_url
        self._redis: Optional[redis.Redis] = None

    async def connect(self):
        if not self._redis:
            self._redis = redis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)

    async def close(self):
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def publish_log(self, repository_id: int, message: str, level: str = "INFO", details: dict = None):
        """Publish a log message to the repository's log stream."""
        if not self._redis:
            await self.connect()

        stream_key = f"repository_logs_stream:{repository_id}"
        
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message,
            "details": details or {}
        }
        
        try:
            # Use Redis Streams (XADD) instead of PubSub to support history
            # Store the entire payload as a JSON string in the 'data' field
            await self._redis.xadd(
                stream_key,
                {"data": json.dumps(payload)},
                maxlen=1000,  # Keep last 1000 logs
                approximate=True
            )
            # Set expiration on the stream key (e.g., 24 hours) to clean up old streams
            await self._redis.expire(stream_key, 86400)
        except Exception as e:
            logger.error(f"Failed to publish log to Redis: {e}")

    async def clear_logs(self, repository_id: int):
        """Clear the log stream for a repository."""
        if not self._redis:
            await self.connect()
        stream_key = f"repository_logs_stream:{repository_id}"
        await self._redis.delete(stream_key)

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
