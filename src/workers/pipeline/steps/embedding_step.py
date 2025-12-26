import time
from celery import current_task
from sqlalchemy import select
from src.database.models import Repository
from src.config.enums import RepositoryStatusEnum
from src.workers.embedding_worker import _generate_repository_embeddings
from src.utils.redis_logger import RedisLogPublisher
from src.utils.logging_config import get_logger
from ..step import PipelineStep
from ..context import PipelineContext

logger = get_logger(__name__)

class EmbeddingGenerationStep(PipelineStep):
    """
    Step 11: Generate embeddings.
    """
    
    async def execute(self, ctx: PipelineContext) -> None:
        publisher = RedisLogPublisher()
        start_time = time.time()
        
        # Re-fetch repo object and update status
        result = await ctx.session.execute(select(Repository).where(Repository.id == ctx.repository_id))
        repo = result.scalar_one()
        ctx.repository = repo
        
        repo.status = RepositoryStatusEnum.EMBEDDING
        await ctx.session.commit()
    
        logger.info(
            "embedding_generation_started",
            repository_id=ctx.repository_id
        )
        await publisher.publish_log(ctx.repository_id, "Generating embeddings...")
    
        # Pass the current Celery task if available, or None
        # We need to access the task context somehow. 
        # Ideally, we pass it in ctx.metadata or construction, but current_task from celery works if running in worker.
        task = current_task
        
        embeddings_generated = await _generate_repository_embeddings(
            ctx.session,
            ctx.repository_id,
            task
        )
        
        ctx.metadata['embeddings_generated'] = embeddings_generated
    
        logger.info(
            "embedding_generation_completed",
            repository_id=ctx.repository_id,
            embeddings_generated=embeddings_generated
        )
        await publisher.publish_log(ctx.repository_id, f"Embedding generation completed. Generated {embeddings_generated} embeddings.", details={"embeddings_generated": embeddings_generated})

        ctx.timings['embedding_generation'] = time.time() - start_time
