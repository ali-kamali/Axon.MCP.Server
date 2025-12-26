import time
from sqlalchemy import select
from src.database.models import Repository
from src.config.enums import RepositoryStatusEnum
from src.extractors.relationship_builder import RelationshipBuilder
from src.utils.redis_logger import RedisLogPublisher
from src.utils.logging_config import get_logger
from ..step import PipelineStep
from ..context import PipelineContext

logger = get_logger(__name__)

class RelationshipBuildingStep(PipelineStep):
    """
    Step 5: Build cross-file relationships.
    Updates repository status to EXTRACTING.
    """
    
    async def execute(self, ctx: PipelineContext) -> None:
        publisher = RedisLogPublisher()
        start_time = time.time()
        
        # Re-fetch repository object as it might have been detached by expunge_all() in previous steps
        # Although PipelineContext tries to hold it, session.expunge_all() acts on the session.
        if not ctx.repository:
             result = await ctx.session.execute(select(Repository).where(Repository.id == ctx.repository_id))
             ctx.repository = result.scalar_one_or_none() # Should be there
             
        if ctx.repository:
            # We need to make sure it's attached.
            # If ctx.repository was set but detached, we might need to merge or re-fetch.
            # Easiest is to always re-fetch if we are going to modify it.
            # But let's check strict state.
             result = await ctx.session.execute(select(Repository).where(Repository.id == ctx.repository_id))
             repo = result.scalar_one()
             repo.status = RepositoryStatusEnum.EXTRACTING
             ctx.repository = repo # Update context
             await ctx.session.commit()
        
        logger.info(
            "relationship_building_started",
            repository_id=ctx.repository_id
        )
        await publisher.publish_log(ctx.repository_id, "Building cross-file relationships...")
    
        relationship_builder = RelationshipBuilder(ctx.session)
        relationships_created = await relationship_builder.build_cross_file_relationships(ctx.repository_id)
        
        ctx.metadata['relationships_created'] = relationships_created
    
        logger.info(
            "relationship_building_completed",
            repository_id=ctx.repository_id,
            relationships_created=relationships_created
        )
        await publisher.publish_log(ctx.repository_id, f"Relationship building completed. Created {relationships_created} relationships.", details={"relationships_created": relationships_created})

        ctx.timings['relationship_building'] = time.time() - start_time
