import asyncio
import time
from src.utils.redis_logger import RedisLogPublisher
from src.utils.logging_config import get_logger
from ..step import PipelineStep
from ..context import PipelineContext

logger = get_logger(__name__)

class DotnetRestoreStep(PipelineStep):
    """
    Step 1.5: Restore .NET dependencies.
    """
    
    async def execute(self, ctx: PipelineContext) -> None:
        if not ctx.repo_path:
            logger.warning("skipping_restore_no_path")
            return
            
        publisher = RedisLogPublisher()
        repo_path = ctx.repo_path
        
        # Check if we need to restore
        has_sln = any(repo_path.glob("*.sln"))
        has_csproj = any(repo_path.glob("**/*.csproj"))
        
        if has_sln or has_csproj:
            start_time = time.time()
            logger.info("dotnet_restore_started", repository_id=ctx.repository_id)
            await publisher.publish_log(ctx.repository_id, "Restoring .NET dependencies...")
            
            try:
                # Use dotnet restore on the repo path
                restore_proc = await asyncio.create_subprocess_exec(
                    "dotnet", "restore", str(repo_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                # Add timeout to prevent hanging indefinitely
                stdout, stderr = await asyncio.wait_for(
                    restore_proc.communicate(),
                    timeout=300 # 5 minutes timeout
                )
                
                if restore_proc.returncode == 0:
                    logger.info("dotnet_restore_completed", repository_id=ctx.repository_id)
                    await publisher.publish_log(ctx.repository_id, ".NET dependencies restored successfully.")
                else:
                    error_out = stderr.decode('utf-8', errors='ignore')
                    logger.warning("dotnet_restore_failed", repository_id=ctx.repository_id, error=error_out)
                    await publisher.publish_log(ctx.repository_id, "Warning: .NET restore failed. Analysis may be incomplete.", level="WARNING")
                    
            except asyncio.TimeoutError:
                logger.warning("dotnet_restore_timeout", repository_id=ctx.repository_id)
                await publisher.publish_log(ctx.repository_id, "Warning: .NET restore timed out. Analysis may be incomplete.", level="WARNING")
                # Ensure process is killed
                try:
                    restore_proc.kill()
                except:
                    pass
            except Exception as e:
                logger.error("dotnet_restore_exception", repository_id=ctx.repository_id, error=str(e))
                # Don't fail the sync, continue with best effort
            
            ctx.timings['dotnet_restore'] = time.time() - start_time
    
    async def can_skip(self, ctx: PipelineContext) -> bool:
        return False
