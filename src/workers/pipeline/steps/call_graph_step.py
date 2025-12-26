import time
from src.config.settings import settings
from src.extractors.call_graph_builder import CallGraphBuilder
from src.utils.redis_logger import RedisLogPublisher
from src.utils.logging_config import get_logger
from ..step import PipelineStep
from ..context import PipelineContext

logger = get_logger(__name__)

class CallGraphStep(PipelineStep):
    """
    Step 7: Build call graph (if enabled).
    """
    
    async def execute(self, ctx: PipelineContext) -> None:
        if not settings.build_call_graph:
            return

        publisher = RedisLogPublisher()
        start_time = time.time()
        
        logger.info(
            "call_graph_building_started",
            repository_id=ctx.repository_id
        )
        await publisher.publish_log(ctx.repository_id, "Building call graph...")
        
        try:
            call_graph_builder = CallGraphBuilder(ctx.session)
            call_relationships_created = await call_graph_builder.build_call_relationships(ctx.repository_id)
            
            ctx.metadata['call_relationships_created'] = call_relationships_created
            
            logger.info(
                "call_graph_building_completed",
                repository_id=ctx.repository_id,
                relationships_created=call_relationships_created
            )
            await publisher.publish_log(ctx.repository_id, f"Call graph building completed. Created {call_relationships_created} relationships.", details={"relationships_created": call_relationships_created})
            
        except Exception as e:
            logger.error(
                "call_graph_building_failed",
                repository_id=ctx.repository_id,
                error=str(e)
            )
            await publisher.publish_log(ctx.repository_id, f"Call graph building failed: {str(e)}", level="ERROR")
            # Continue even if call graph building fails

        ctx.timings['call_graph'] = time.time() - start_time
