"""
Celery tasks for embedding generation.
"""

from celery import shared_task
from typing import List
import asyncio
import traceback
from sqlalchemy import select

from src.workers.celery_app import celery_app
from src.workers.utils import _run_with_engine_cleanup
from src.database.session import AsyncSessionLocal
from src.database.models import Chunk, File
from src.embeddings.generator import EmbeddingGenerator
from src.vector_store.pgvector_store import PgVectorStore
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


async def _generate_repository_embeddings(
    session,
    repository_id: int,
    task=None
) -> int:
    """
    Generate embeddings for all chunks in repository.
    
    Args:
        session: Database session
        repository_id: Repository ID
        task: Celery task (for progress updates)
        
    Returns:
        Number of embeddings generated
    """
    # Get all chunks for repository
    result = await session.execute(
        select(Chunk)
        .join(File)
        .where(File.repository_id == repository_id)
    )
    chunks = result.scalars().all()
    
    if not chunks:
        logger.warning(
            "no_chunks_found_for_embeddings",
            repository_id=repository_id
        )
        return 0
    
    logger.info(
        "generating_embeddings",
        repository_id=repository_id,
        chunk_count=len(chunks)
    )
    
    # Prepare chunks for embedding
    chunk_data = [
        {'id': chunk.id, 'content': chunk.content}
        for chunk in chunks
    ]
    
    # Generate embeddings in batches
    generator = EmbeddingGenerator()
    embedding_results = await generator.generate_embeddings(chunk_data)
    
    # Store in vector store
    vector_store = PgVectorStore(session)
    stored = await vector_store.store_embeddings(embedding_results)
    
    # Update progress
    if task:
        task.update_state(
            state='PROGRESS',
            meta={
                'status': 'embedding',
                'embeddings_generated': stored,
                'phase': 'embedding_generation'
            }
        )
    
    logger.info(
        "repository_embeddings_generated",
        repository_id=repository_id,
        count=stored
    )
    
    return stored


@celery_app.task(
    bind=True,
    name="src.workers.tasks.generate_embeddings_task",
    max_retries=3
)
def generate_embeddings_task(self, chunk_ids: List[int]):
    """
    Generate embeddings for specific chunks.
    
    Args:
        chunk_ids: List of chunk IDs
        
    Returns:
        dict: Generation result
    """
    logger.info(
        "generate_embeddings_task_started",
        chunk_count=len(chunk_ids),
        task_id=self.request.id
    )
    
    try:
        result = asyncio.run(_run_with_engine_cleanup(_generate_embeddings_async(chunk_ids)))
        return result
    except Exception as e:
        error_msg = f"Failed to generate embeddings: {str(e)}"
        logger.error(
            "generate_embeddings_task_failed",
            chunk_count=len(chunk_ids),
            error=error_msg,
            traceback=traceback.format_exc()
        )
        raise self.retry(exc=e, countdown=30 * (2 ** self.request.retries))


async def _generate_embeddings_async(chunk_ids: List[int]):
    """Async implementation of embedding generation."""
    
    # Use AsyncSessionLocal directly for manual transaction management
    async with AsyncSessionLocal() as session:
        try:
            # Get chunks
            result = await session.execute(
                select(Chunk).where(Chunk.id.in_(chunk_ids))
            )
            chunks = result.scalars().all()
            
            if not chunks:
                error_msg = f"Failed to generate embeddings: No chunks found for IDs {chunk_ids}"
                logger.warning("no_chunks_found", chunk_ids=chunk_ids, error=error_msg)
                return {"status": "error", "error": error_msg}
            
            # Prepare chunk data
            chunk_data = [
                {'id': chunk.id, 'content': chunk.content}
                for chunk in chunks
            ]
            
            # Generate embeddings
            generator = EmbeddingGenerator()
            embedding_results = await generator.generate_embeddings(chunk_data)
            
            # Store embeddings
            vector_store = PgVectorStore(session)
            stored = await vector_store.store_embeddings(embedding_results)
            
            await session.commit()
            
            logger.info(
                "embeddings_generated_successfully",
                chunk_count=len(chunk_ids),
                embeddings_stored=stored
            )
            
            return {
                "status": "success",
                "embeddings_generated": stored,
                "chunk_count": len(chunks)
            }
            
        except Exception as e:
            error_msg = f"Failed to generate embeddings: {str(e)}"
            logger.error(
                "embedding_generation_failed",
                chunk_count=len(chunk_ids),
                error=error_msg,
                traceback=traceback.format_exc()
            )
            await session.rollback()
            raise
