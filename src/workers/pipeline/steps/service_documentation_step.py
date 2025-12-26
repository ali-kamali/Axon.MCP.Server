import time
from datetime import datetime
from sqlalchemy import select
from src.database.models import Service
from src.generators.service_doc_generator import ServiceDocGenerator
from src.utils.redis_logger import RedisLogPublisher
from src.utils.logging_config import get_logger
from ..step import PipelineStep
from ..context import PipelineContext

logger = get_logger(__name__)

class ServiceDocumentationStep(PipelineStep):
    """
    Step 11.6: Generate Service Documentation (after service detection).
    """
    
    async def execute(self, ctx: PipelineContext) -> None:
        publisher = RedisLogPublisher()
        start_time = time.time()
        
        services_documented = 0
        try:
            logger.info(
                "service_documentation_started",
                repository_id=ctx.repository_id
            )
            await publisher.publish_log(ctx.repository_id, "Generating service documentation...")
            
            doc_generator = ServiceDocGenerator(ctx.session)
            
            # Get all services for this repository (including ones just detected)
            services_result = await ctx.session.execute(
                select(Service).filter(Service.repository_id == ctx.repository_id)
            )
            all_services = services_result.scalars().all()
            
            for service in all_services:
                try:
                    # Generate documentation
                    doc_content = await doc_generator.generate_service_doc(service)
                    
                    # Save to filesystem
                    doc_path = await doc_generator.save_documentation(service, doc_content)
                    
                    # Update service record
                    service.documentation_path = doc_path
                    service.last_documented_at = datetime.utcnow()
                    
                    services_documented += 1
                    logger.debug(f"Documented service: {service.name}")
                except Exception as e:
                    logger.error(
                        "service_documentation_failed_for_service",
                        service_name=service.name,
                        error=str(e)
                    )
                    # Continue with other services
                    continue
            
            await ctx.session.commit()
            
            ctx.metadata['services_documented'] = services_documented
            
            logger.info(
                "service_documentation_completed",
                repository_id=ctx.repository_id,
                services_documented=services_documented
            )
            await publisher.publish_log(
                ctx.repository_id,
                f"Service documentation generation completed. Documented {services_documented} services.",
                details={"services_documented": services_documented}
            )
        except Exception as e:
            logger.error(
                "service_documentation_failed",
                repository_id=ctx.repository_id,
                error=str(e)
            )
            await publisher.publish_log(ctx.repository_id, f"Service documentation logic failed: {str(e)}", level="ERROR")
            # Continue
            
        ctx.timings['service_doc_generation'] = time.time() - start_time
