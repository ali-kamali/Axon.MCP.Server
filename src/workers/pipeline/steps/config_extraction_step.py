import time
from src.config.settings import settings
from src.utils.redis_logger import RedisLogPublisher
from src.utils.logging_config import get_logger
from ..step import PipelineStep
from ..context import PipelineContext

logger = get_logger(__name__)

class ConfigExtractionStep(PipelineStep):
    """
    Step 7.6: Extract configuration (if enabled).
    """
    
    async def execute(self, ctx: PipelineContext) -> None:
        if not settings.extract_configuration:
            return
            
        if not ctx.repo_path:
             return

        publisher = RedisLogPublisher()
        start_time = time.time()
        
        logger.info(
            "configuration_extraction_started",
            repository_id=ctx.repository_id
        )
        await publisher.publish_log(ctx.repository_id, "Extracting configuration...")
        
        try:
            # Import locally
            from src.extractors.config_extractor import ConfigExtractor
            
            config_extractor = ConfigExtractor(ctx.session)
            configs_found = await config_extractor.extract_configuration(ctx.repository_id, ctx.repo_path)
            
            ctx.metadata['configs_found'] = configs_found
            
            logger.info(
                "configuration_extraction_completed",
                repository_id=ctx.repository_id,
                configs_found=configs_found
            )
            await publisher.publish_log(
                ctx.repository_id,
                f"Configuration extraction completed. Found {configs_found} configurations.",
                details={"configs_found": configs_found}
            )
            
        except Exception as e:
            logger.error(
                "configuration_extraction_failed",
                repository_id=ctx.repository_id,
                error=str(e)
            )
            await publisher.publish_log(ctx.repository_id, f"Configuration extraction failed: {str(e)}", level="ERROR")
            # Continue

        ctx.timings['config_extraction'] = time.time() - start_time
