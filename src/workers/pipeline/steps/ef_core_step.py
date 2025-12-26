import time
import traceback
from src.config.settings import settings
from src.config.enums import LanguageEnum
from src.parsers import ParserFactory
from src.analyzers.ef_analyzer import EfCoreAnalyzer
from src.utils.redis_logger import RedisLogPublisher
from src.utils.logging_config import get_logger
from ..step import PipelineStep
from ..context import PipelineContext

logger = get_logger(__name__)

class EfCoreExtractionStep(PipelineStep):
    """
    Step 7.7: Extract EF Core entities (if enabled).
    """
    
    async def execute(self, ctx: PipelineContext) -> None:
        if not settings.extract_ef_entities:
            return

        publisher = RedisLogPublisher()
        start_time = time.time()
        
        logger.info(
            "ef_entity_extraction_started",
            repository_id=ctx.repository_id
        )
        await publisher.publish_log(ctx.repository_id, "Extracting EF Core entities...")
        
        try:
            # Robust initialization logic for Roslyn instance
            roslyn_instance = None
            
            # Try getting it from ParserFactory (should be initialized by RoslynInitStep)
            try:
                parser = ParserFactory.get_parser(LanguageEnum.CSHARP)
                if hasattr(parser, 'roslyn'):
                    roslyn_instance = parser.roslyn
            except Exception as e:
                logger.error("roslyn_fallback_acquisition_failed", error=str(e), traceback=traceback.format_exc())
                pass
            
            # Ultimate fallback: Direct instantiation if factory failed (legacy safety net)
            if not roslyn_instance:
                try:
                    logger.info("attempting_roslyn_direct_instantiation")
                    from src.parsers.hybrid_parser import HybridCSharpParser
                    tmp_parser = HybridCSharpParser()
                    if hasattr(tmp_parser, 'roslyn') and tmp_parser.roslyn.is_available():
                        roslyn_instance = tmp_parser.roslyn
                        logger.info("roslyn_direct_instantiation_success")
                except Exception as e:
                    logger.error("roslyn_direct_instantiation_failed", error=str(e), traceback=traceback.format_exc())
            
            if roslyn_instance:
                ef_analyzer = EfCoreAnalyzer(roslyn_instance)
                ef_result = await ef_analyzer.analyze_repository(ctx.session, ctx.repository_id, str(ctx.repo_path))
                ef_entities_found = ef_result.get("entities_found", 0)
                
                ctx.metadata['ef_entities_found'] = ef_entities_found
                
                logger.info(
                    "ef_entity_extraction_completed",
                    repository_id=ctx.repository_id,
                    entities_found=ef_entities_found
                )
                await publisher.publish_log(
                    ctx.repository_id, 
                    f"EF Core entity extraction completed. Found {ef_entities_found} entities.", 
                    details={"entities_found": ef_entities_found}
                )
            else:
                logger.warning("ef_entity_extraction_skipped_no_roslyn", repository_id=ctx.repository_id)
                await publisher.publish_log(ctx.repository_id, "Warning: EF Core extraction skipped (Roslyn unavailable).", level="WARNING")

        except Exception as e:
            logger.error(
                "ef_entity_extraction_failed",
                repository_id=ctx.repository_id,
                error=str(e),
                traceback=traceback.format_exc()
            )
            await publisher.publish_log(ctx.repository_id, f"EF Core entity extraction failed: {str(e)}", level="ERROR")
            # Continue

        ctx.timings['ef_extraction'] = time.time() - start_time
