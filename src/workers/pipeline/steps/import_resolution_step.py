import time
from src.config.settings import settings
from src.extractors.import_resolver import ImportRelationshipBuilder
from src.utils.redis_logger import RedisLogPublisher
from src.utils.logging_config import get_logger
from ..step import PipelineStep
from ..context import PipelineContext

logger = get_logger(__name__)

class ImportResolutionStep(PipelineStep):
    """
    Step 6: Build import relationships (if enabled).
    """
    
    async def execute(self, ctx: PipelineContext) -> None:
        if not settings.extract_imports:
            return

        publisher = RedisLogPublisher()
        start_time = time.time()
        
        logger.info(
            "import_relationship_building_started",
            repository_id=ctx.repository_id
        )
        await publisher.publish_log(ctx.repository_id, "Building import relationships...")
        
        try:
            if not ctx.repo_path:
                 raise ValueError("Repo path missing for import resolution")

            import_builder = ImportRelationshipBuilder(ctx.session, ctx.repo_path)
            import_relationships_created = await import_builder.build_import_relationships(ctx.repository_id)
            
            ctx.metadata['import_relationships_created'] = import_relationships_created
            
            logger.info(
                "import_relationship_building_completed",
                repository_id=ctx.repository_id,
                relationships_created=import_relationships_created
            )
            await publisher.publish_log(ctx.repository_id, f"Import relationship building completed. Created {import_relationships_created} relationships.", details={"relationships_created": import_relationships_created})
            
        except Exception as e:
            logger.error(
                "import_relationship_building_failed",
                repository_id=ctx.repository_id,
                error=str(e)
            )
            await publisher.publish_log(ctx.repository_id, f"Import relationship building failed: {str(e)}", level="ERROR")
            # Continue even if import resolution fails

        ctx.timings['import_resolution'] = time.time() - start_time
