import time
from src.config.settings import settings
from src.utils.redis_logger import RedisLogPublisher
from src.utils.logging_config import get_logger
from ..step import PipelineStep
from ..context import PipelineContext

logger = get_logger(__name__)

class DependencyExtractionStep(PipelineStep):
    """
    Step 7.5: Extract dependencies (if enabled).
    """
    
    async def execute(self, ctx: PipelineContext) -> None:
        if not settings.extract_dependencies:
            return

        if not ctx.repo_path:
             logger.warning("skipping_dependency_extraction_no_path")
             return

        publisher = RedisLogPublisher()
        start_time = time.time()
        
        logger.info(
            "dependency_extraction_started",
            repository_id=ctx.repository_id
        )
        await publisher.publish_log(ctx.repository_id, "Extracting package dependencies...")
        
        try:
            # Import strictly locally as in original code
            from src.extractors.dependency_extractor import DependencyExtractor
            
            dep_extractor = DependencyExtractor(ctx.session)
            dependencies_found = await dep_extractor.extract_dependencies(ctx.repository_id, ctx.repo_path)
            
            ctx.metadata['dependencies_found'] = dependencies_found
            
            logger.info(
                "dependency_extraction_completed",
                repository_id=ctx.repository_id,
                dependencies_found=dependencies_found
            )
            await publisher.publish_log(
                ctx.repository_id,
                f"Dependency extraction completed. Found {dependencies_found} dependencies.",
                details={"dependencies_found": dependencies_found}
            )
            
        except Exception as e:
            logger.error(
                "dependency_extraction_failed",
                repository_id=ctx.repository_id,
                error=str(e)
            )
            await publisher.publish_log(ctx.repository_id, f"Dependency extraction failed: {str(e)}", level="ERROR")
            # Continue even if dependency extraction fails

        ctx.timings['dependency_extraction'] = time.time() - start_time
