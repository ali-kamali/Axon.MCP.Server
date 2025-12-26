import time
import traceback
from src.analyzers.service_boundary_analyzer import ServiceBoundaryAnalyzer
from src.utils.redis_logger import RedisLogPublisher
from src.utils.logging_config import get_logger
from ..step import PipelineStep
from ..context import PipelineContext

logger = get_logger(__name__)

class ServiceDetectionStep(PipelineStep):
    """
    Step 11.5: Detect Services (after all symbols and relationships are committed).
    """
    
    async def execute(self, ctx: PipelineContext) -> None:
        publisher = RedisLogPublisher()
        start_time = time.time()
        
        services_detected = 0
        try:
            logger.info(
                "service_detection_started",
                repository_id=ctx.repository_id
            )
            await publisher.publish_log(ctx.repository_id, "Detecting service boundaries...")
            
            service_analyzer = ServiceBoundaryAnalyzer()
            services = await service_analyzer.detect_services(ctx.repository, ctx.session)
            
            # Services are either created or updated (upsert logic in analyzer typically)
            # We just need to add new ones to session and ensure persistence
            for service in services:
                ctx.session.add(service)
            
            await ctx.session.commit()
            services_detected = len(services)
            
            ctx.metadata['services_detected'] = services_detected
            
            logger.info(
                "service_detection_completed",
                repository_id=ctx.repository_id,
                services_detected=services_detected
            )
            await publisher.publish_log(
                ctx.repository_id,
                f"Service detection completed. Detected {services_detected} services.",
                details={"services_detected": services_detected}
            )
        except Exception as e:
            # Don't fail the entire sync if service detection fails
            logger.error(
                "service_detection_failed",
                repository_id=ctx.repository_id,
                error=str(e),
                traceback=traceback.format_exc()
            )
            await publisher.publish_log(ctx.repository_id, f"Service detection failed: {str(e)}", level="ERROR")
            # Continue
            
        ctx.timings['service_detection'] = time.time() - start_time
