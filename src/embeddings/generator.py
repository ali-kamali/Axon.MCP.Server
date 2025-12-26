from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import asyncio
import time

# Optional import for OpenAI
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    AsyncOpenAI = None

from sentence_transformers import SentenceTransformer
from src.config.settings import settings
from src.utils.logging_config import get_logger
from src.utils.metrics import embedding_generation_duration, embeddings_generated_total

logger = get_logger(__name__)


@dataclass
class EmbeddingResult:
    """Result of embedding generation."""
    chunk_id: int
    vector: List[float]
    model_name: str
    model_version: str
    dimension: int


class EmbeddingGenerator:
    """Generates vector embeddings using OpenAI or local models."""
    
    def __init__(self):
        """Initialize embedding generator."""
        self.provider = settings.embedding_provider
        
        if self.provider == "openai":
            if not OPENAI_AVAILABLE:
                raise ImportError(
                    "Failed to initialize embedding generator: OpenAI package not installed. Install with: pip install openai"
                )
            if not settings.openai_api_key:
                raise ValueError("Failed to initialize embedding generator: OpenAI API key required when provider is 'openai'")
            self.client = AsyncOpenAI(api_key=settings.openai_api_key)
            self.model_name = settings.openai_embedding_model
            self.dimension = settings.openai_embedding_dimension
        else:
            # Local model using sentence-transformers
            logger.info(
                "loading_local_embedding_model",
                model=settings.local_embedding_model
            )
            self.model = SentenceTransformer(settings.local_embedding_model)
            self.model_name = settings.local_embedding_model
            self.dimension = self.model.get_sentence_embedding_dimension()
        
        logger.info(
            "embedding_generator_initialized",
            provider=self.provider,
            model=self.model_name,
            dimension=self.dimension
        )
    
    async def generate_embeddings(
        self,
        chunks: List[Dict[str, Any]],
        batch_size: Optional[int] = None
    ) -> List[EmbeddingResult]:
        """
        Generate embeddings for chunks.
        
        Args:
            chunks: List of dicts with 'id' and 'content' keys
            batch_size: Batch size for processing
            
        Returns:
            List of EmbeddingResults
        """
        batch_size = batch_size or settings.embedding_batch_size
        results = []
        
        # Process in batches
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            
            try:
                if self.provider == "openai":
                    batch_results = await self._generate_openai_embeddings(batch)
                else:
                    batch_results = await self._generate_local_embeddings(batch)
                
                results.extend(batch_results)
                
                embeddings_generated_total.labels(
                    model=self.model_name,
                    status="success"
                ).inc(len(batch))
                
                logger.info(
                    "embedding_batch_completed",
                    batch_num=i // batch_size + 1,
                    batch_size=len(batch),
                    total_processed=len(results)
                )
                
            except Exception as e:
                error_msg = f"Failed to generate embeddings: {str(e)}"
                logger.error(
                    "embedding_batch_failed",
                    batch_num=i // batch_size + 1,
                    error=error_msg
                )
                embeddings_generated_total.labels(
                    model=self.model_name,
                    status="error"
                ).inc(len(batch))
                # Continue with next batch
                continue
        
        return results
    
    async def _generate_openai_embeddings(
        self,
        chunks: List[Dict[str, Any]]
    ) -> List[EmbeddingResult]:
        """Generate embeddings using OpenAI API."""
        start_time = time.time()
        
        texts = [chunk['content'] for chunk in chunks]
        
        try:
            response = await self.client.embeddings.create(
                model=self.model_name,
                input=texts,
                encoding_format="float"
            )
            
            results = []
            for i, chunk in enumerate(chunks):
                results.append(EmbeddingResult(
                    chunk_id=chunk['id'],
                    vector=response.data[i].embedding,
                    model_name=self.model_name,
                    model_version="1.0",  # Could extract from response
                    dimension=self.dimension
                ))
            
            duration = time.time() - start_time
            embedding_generation_duration.labels(model=self.model_name).observe(duration)
            
            return results
            
        except Exception as e:
            error_msg = f"Failed to generate OpenAI embeddings: {str(e)}"
            logger.error(
                "openai_embedding_failed",
                error=error_msg,
                chunk_count=len(chunks)
            )
            raise
    
    async def _generate_local_embeddings(
        self,
        chunks: List[Dict[str, Any]]
    ) -> List[EmbeddingResult]:
        """Generate embeddings using local model."""
        start_time = time.time()
        
        texts = [chunk['content'] for chunk in chunks]
        
        try:
            # Run in thread pool since sentence-transformers is synchronous
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None,
                self.model.encode,
                texts
            )
            
            results = []
            for i, chunk in enumerate(chunks):
                results.append(EmbeddingResult(
                    chunk_id=chunk['id'],
                    vector=embeddings[i].tolist(),
                    model_name=self.model_name,
                    model_version="1.0",
                    dimension=self.dimension
                ))
            
            duration = time.time() - start_time
            embedding_generation_duration.labels(model=self.model_name).observe(duration)
            
            logger.info(
                "local_embeddings_generated",
                chunk_count=len(chunks),
                duration_seconds=round(duration, 2)
            )
            
            return results
            
        except Exception as e:
            error_msg = f"Failed to generate local embeddings: {str(e)}"
            logger.error(
                "local_embedding_failed",
                error=error_msg,
                chunk_count=len(chunks)
            )
            raise
    
    async def generate_single_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector
        """
        chunks = [{'id': 0, 'content': text}]
        results = await self.generate_embeddings(chunks, batch_size=1)
        
        if results:
            return results[0].vector
        return []

