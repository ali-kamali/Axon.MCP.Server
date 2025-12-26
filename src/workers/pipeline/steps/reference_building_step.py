import time
from src.extractors.reference_builder import ReferenceBuilder
from src.parsers import ParserFactory
from src.config.enums import LanguageEnum
from src.utils.redis_logger import RedisLogPublisher
from src.utils.logging_config import get_logger
from ..step import PipelineStep
from ..context import PipelineContext

logger = get_logger(__name__)

class ReferenceBuildingStep(PipelineStep):
    """
    Step 4.5: Build reference relationships (now that all symbols exist).
    Uses Roslyn if available.
    """
    
    async def execute(self, ctx: PipelineContext) -> None:
        publisher = RedisLogPublisher()
        start_time = time.time()
        
        logger.info("reference_building_started", repository_id=ctx.repository_id)
        await publisher.publish_log(ctx.repository_id, "Building reference relationships...")

        try:
            # Try to reuse Roslyn instance to avoid overhead
            roslyn_instance = None
            try:
                parser = ParserFactory.get_parser(LanguageEnum.CSHARP)
                if hasattr(parser, 'roslyn'):
                    roslyn_instance = parser.roslyn
            except Exception:
                pass

            reference_builder = ReferenceBuilder(ctx.session, roslyn_analyzer=roslyn_instance)
            ref_relations = await reference_builder.build_all_references(ctx.repository_id)
            
            ctx.metadata['references_created'] = ref_relations
            
            logger.info(
                "reference_building_completed",
                repository_id=ctx.repository_id,
                references_created=ref_relations
            )
            await publisher.publish_log(
                ctx.repository_id, 
                f"Reference building completed. Created {ref_relations} references.",
                details={"references_created": ref_relations}
            )
            
        except Exception as e:
            logger.error(
                "reference_building_failed",
                repository_id=ctx.repository_id,
                error=str(e)
            )
            await publisher.publish_log(ctx.repository_id, f"Reference building failed: {str(e)}", level="ERROR")
            # Continue - don't fail entire sync

        ctx.timings['reference_building'] = time.time() - start_time
