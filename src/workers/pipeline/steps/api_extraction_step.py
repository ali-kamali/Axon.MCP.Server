import time
from src.config.settings import settings
from src.extractors.api_extractor import ApiEndpointExtractor
from src.utils.redis_logger import RedisLogPublisher
from src.utils.logging_config import get_logger
from ..step import PipelineStep
from ..context import PipelineContext

logger = get_logger(__name__)

class ApiExtractionStep(PipelineStep):
    """
    Step 4: Extract API endpoints (if enabled).
    """
    
    async def execute(self, ctx: PipelineContext) -> None:
        if not settings.extract_api_endpoints:
            return

        publisher = RedisLogPublisher()
        start_time = time.time()
        
        logger.info(
            "api_endpoint_extraction_started",
            repository_id=ctx.repository_id
        )
        await publisher.publish_log(ctx.repository_id, "Starting API endpoint extraction...")
        
        try:
            # Re-fetch objects if needed or assume session is clean
            api_extractor = ApiEndpointExtractor(ctx.session)
            endpoints = await api_extractor.extract_endpoints(ctx.repository_id)
            await api_extractor.save_endpoints(endpoints)
            await ctx.session.commit()  # Commit endpoints to database
            
            api_endpoints_count = len(endpoints)
            ctx.metadata['api_endpoints_count'] = api_endpoints_count
            
            logger.info(
                "api_endpoint_extraction_completed",
                repository_id=ctx.repository_id,
                endpoints_found=api_endpoints_count
            )
            await publisher.publish_log(ctx.repository_id, f"API endpoint extraction completed. Found {api_endpoints_count} endpoints.", details={"endpoints_found": api_endpoints_count})
            
        except Exception as e:
            logger.error(
                "api_endpoint_extraction_failed",
                repository_id=ctx.repository_id,
                error=str(e)
            )
            await publisher.publish_log(ctx.repository_id, f"API endpoint extraction failed: {str(e)}", level="ERROR")
            # Continue even if API extraction fails

        ctx.timings['api_extraction'] = time.time() - start_time
