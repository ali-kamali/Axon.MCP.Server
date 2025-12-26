from typing import Optional, List
import json
import hashlib
from src.config.settings import settings
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

try:
    import redis
except ImportError:
    redis = None


class EmbeddingCache:
    """Cache for embedding vectors using Redis."""
    
    def __init__(self):
        """Initialize Redis cache."""
        self.redis_client = None
        self.ttl = 86400 * 7  # 7 days
        
        # Check if Redis is enabled
        if not settings.redis_cache_enabled:
            logger.info("embedding_cache_disabled", message="Redis caching disabled via configuration")
            return
        
        if redis is None:
            logger.warning("redis_not_installed", message="Redis library not installed, embedding cache disabled")
            return
        
        # Try to connect to Redis
        try:
            self.redis_client = redis.from_url(
                settings.redis_url,
                max_connections=settings.redis_max_connections,
                decode_responses=False  # Store binary data
            )
            # Test connection
            self.redis_client.ping()
            logger.info("embedding_cache_initialized")
        except Exception as e:
            # Log as warning since Redis is optional
            logger.warning("embedding_cache_init_failed", error=str(e), message="Embedding cache disabled, application will continue without cache")
            self.redis_client = None
    
    def get(self, content_hash: str, model_name: str) -> Optional[List[float]]:
        """
        Get cached embedding.
        
        Args:
            content_hash: Hash of content
            model_name: Model name
            
        Returns:
            Embedding vector if cached, None otherwise
        """
        if not self.redis_client:
            return None
        
        try:
            key = self._make_key(content_hash, model_name)
            cached = self.redis_client.get(key)
            
            if cached:
                logger.debug("embedding_cache_hit", key=key)
                return json.loads(cached)
            
            logger.debug("embedding_cache_miss", key=key)
            return None
            
        except Exception as e:
            logger.error("embedding_cache_get_failed", error=str(e))
            return None
    
    def set(
        self,
        content_hash: str,
        model_name: str,
        embedding: List[float]
    ) -> bool:
        """
        Cache embedding.
        
        Args:
            content_hash: Hash of content
            model_name: Model name
            embedding: Embedding vector
            
        Returns:
            True if successful
        """
        if not self.redis_client:
            return False
        
        try:
            key = self._make_key(content_hash, model_name)
            value = json.dumps(embedding)
            
            self.redis_client.setex(key, self.ttl, value)
            logger.debug("embedding_cached", key=key)
            return True
            
        except Exception as e:
            logger.error("embedding_cache_set_failed", error=str(e))
            return False
    
    def _make_key(self, content_hash: str, model_name: str) -> str:
        """Create cache key."""
        return f"embedding:{model_name}:{content_hash}"
    
    @staticmethod
    def hash_content(content: str) -> str:
        """Generate hash for content."""
        return hashlib.sha256(content.encode()).hexdigest()

