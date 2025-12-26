import time
from src.utils.redis_logger import RedisLogPublisher
from src.utils.logging_config import get_logger
from src.parsers import ParserFactory
from src.config.enums import LanguageEnum
from ..step import PipelineStep
from ..context import PipelineContext

logger = get_logger(__name__)

class RoslynInitStep(PipelineStep):
    """
    Step 1.6: Initialize Roslyn Project Context.
    Loads the solution or project into the persistent Roslyn process.
    """
    
    async def execute(self, ctx: PipelineContext) -> None:
        if not ctx.repo_path:
            return
            
        publisher = RedisLogPublisher()
        repo_path = ctx.repo_path
        start_time = time.time()
        
        try:
            csharp_parser = ParserFactory.get_parser(LanguageEnum.CSHARP)
            
            # Check if this parser supports Roslyn
            if hasattr(csharp_parser, 'roslyn') and csharp_parser.roslyn.is_available():
                logger.info("initializing_roslyn_context", repository_id=ctx.repository_id)
                await publisher.publish_log(ctx.repository_id, "Initializing Roslyn project context...")
                
                context_loaded = False
                
                # Prioritize Solution files (.sln) - Sort by length to prefer root
                sln_files = sorted(list(repo_path.glob("*.sln")), key=lambda p: len(str(p)))
                if sln_files:
                    sln_path = str(sln_files[0])
                    logger.info("opening_solution", path=sln_path)
                    success = await csharp_parser.roslyn.open_solution(sln_path)
                    if success:
                        context_loaded = True
                        logger.info("roslyn_solution_opened", path=sln_path)
                        await publisher.publish_log(ctx.repository_id, f"Loaded solution: {sln_files[0].name}")
                
                # Fallback to Project files (.csproj)
                if not context_loaded:
                    csproj_files = sorted(list(repo_path.glob("**/*.csproj")), key=lambda p: len(str(p)))
                    if csproj_files:
                        proj_path = str(csproj_files[0])
                        logger.info("opening_project", path=proj_path)
                        success = await csharp_parser.roslyn.open_project(proj_path)
                        if success:
                            context_loaded = True
                            logger.info("roslyn_project_opened", path=proj_path)
                            await publisher.publish_log(ctx.repository_id, f"Loaded project: {csproj_files[0].name}")
                
                if not context_loaded:
                    logger.warning("roslyn_context_load_failed", repository_id=ctx.repository_id)
                    await publisher.publish_log(ctx.repository_id, "Warning: No valid .sln or .csproj found. Roslyn analysis will fall back to ad-hoc mode.", level="WARNING")
        
        except Exception as e:
            logger.error("roslyn_initialization_error", repository_id=ctx.repository_id, error=str(e))
            # Don't fail the sync, just log and continue
            await publisher.publish_log(ctx.repository_id, f"Warning: Roslyn initialization failed: {str(e)}", level="WARNING")
            
        ctx.timings['roslyn_init'] = time.time() - start_time
