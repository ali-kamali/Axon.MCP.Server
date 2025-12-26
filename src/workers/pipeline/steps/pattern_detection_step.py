import time
from src.config.settings import settings
from src.extractors.pattern_detector import PatternDetector
from src.utils.redis_logger import RedisLogPublisher
from src.utils.logging_config import get_logger
from ..step import PipelineStep
from ..context import PipelineContext

logger = get_logger(__name__)

class PatternDetectionStep(PipelineStep):
    """
    Step 8: Detect patterns (if enabled).
    """
    
    async def execute(self, ctx: PipelineContext) -> None:
        if not settings.detect_patterns:
            return

        publisher = RedisLogPublisher()
        start_time = time.time()
        
        logger.info(
            "pattern_detection_started",
            repository_id=ctx.repository_id
        )
        await publisher.publish_log(ctx.repository_id, "Detecting patterns...")
        
        try:
            pattern_detector = PatternDetector(ctx.session)
            patterns = await pattern_detector.detect_patterns(ctx.repository_id)
            patterns_detected = len(patterns)
            
            ctx.metadata['patterns_detected'] = patterns_detected
            
            logger.info(
                "pattern_detection_completed",
                repository_id=ctx.repository_id,
                patterns_found=patterns_detected
            )
            await publisher.publish_log(ctx.repository_id, f"Pattern detection completed. Found {patterns_detected} patterns.", details={"patterns_found": patterns_detected})
            
        except Exception as e:
            logger.error(
                "pattern_detection_failed",
                repository_id=ctx.repository_id,
                error=str(e)
            )
            await publisher.publish_log(ctx.repository_id, f"Pattern detection failed: {str(e)}", level="ERROR")
            # Continue

        ctx.timings['pattern_detection'] = time.time() - start_time
