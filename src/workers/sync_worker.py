"""
Celery tasks for repository synchronization.
"""

from celery import shared_task
from datetime import datetime
import asyncio
import traceback

from sqlalchemy import select, func

from src.workers.celery_app import celery_app
from src.workers.utils import _run_with_engine_cleanup, _count_symbols
from src.workers.summary_worker import _generate_module_summaries
from src.database.session import AsyncSessionLocal
from src.database.models import Repository, Job, File
from src.config.enums import RepositoryStatusEnum, JobStatusEnum, SourceControlProviderEnum
from src.utils.logging_config import get_logger
from src.utils.redis_logger import RedisLogPublisher
from src.workers.distributed_lock import get_distributed_lock
from src.parsers import ParserFactory

logger = get_logger(__name__)


@celery_app.task(bind=True, name="src.workers.tasks.sync_repository", max_retries=3, time_limit=14400)
def sync_repository(self, repository_id: int):
    """
    Sync repository: clone, parse, extract, and embed.
    
    This is the main orchestration task that handles the complete
    repository processing pipeline.
    
    Args:
        repository_id: Repository ID in database
        
    Returns:
        dict: Result summary with status and metrics
    """
    logger.info(
        "repository_sync_task_started",
        repository_id=repository_id,
        task_id=self.request.id
    )
    
    try:
        # Run async task - handle both async exceptions and asyncio failures
        # Use helper to ensure proper engine cleanup after asyncio.run()
        result = asyncio.run(_run_with_engine_cleanup(_sync_repository_async(self, repository_id)))
        return result
    except asyncio.CancelledError as e:
        # Task was cancelled (e.g., worker shutdown)
        error_msg = f"Failed to sync repository: {str(e)}"
        logger.warning(
            "repository_sync_task_cancelled",
            repository_id=repository_id,
            error=error_msg
        )
        # Don't retry on cancellation
        return {
            "status": "cancelled",
            "repository_id": repository_id,
            "error": error_msg
        }
    except RuntimeError as e:
        # asyncio.run() failures (e.g., event loop issues)
        error_msg = f"Failed to sync repository: {str(e)}"
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            logger.error(
                "repository_sync_asyncio_error",
                repository_id=repository_id,
                error=error_msg,
                message="Event loop conflict - this should not happen in production"
            )
            # Don't retry on asyncio errors
            raise
        # Other RuntimeErrors should retry
        logger.error(
            "repository_sync_runtime_error",
            repository_id=repository_id,
            error=error_msg,
            traceback=traceback.format_exc()
        )
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
    except Exception as e:
        error_msg = f"Failed to sync repository: {str(e)}"
        logger.error(
            "repository_sync_task_failed",
            repository_id=repository_id,
            error=error_msg,
            traceback=traceback.format_exc()
        )
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


async def _sync_repository_async(task, repository_id: int):
    """Async implementation of repository sync."""
    
    # Initialize resource variables for safe cleanup
    session = None
    publisher = None
    
    # Initialize state variables for exception handler safety
    job_started_at = None
    job_started_at_ts = None
    
    files_processed = 0
    chunks_created = 0
    embeddings_generated = 0
    
    # Use distributed lock to prevent concurrent processing
    lock = get_distributed_lock()
    resource_key = f"repository:{repository_id}"
    
    publisher = RedisLogPublisher()
    await publisher.connect()
    
    # Clear previous logs for this repository to ensure fresh logs for the new sync
    await publisher.clear_logs(repository_id)
    
    try:
    
        with lock.acquire(resource_key, timeout=3600) as acquired:
            if not acquired:
                logger.warning(
                    "repository_sync_already_in_progress",
                    repository_id=repository_id
                )
                return {
                    "status": "skipped",
                    "reason": "Repository is already being processed",
                    "repository_id": repository_id
                }
        
            # Use AsyncSessionLocal directly for manual transaction management
            # This is needed because we have intermediate commits for progress tracking
            async with AsyncSessionLocal() as session:
                session.expire_on_commit = False # Fix: Prevent attribute expiration on commit
                
                # Initialize to None for exception handler
                repo = None
                job = None
            
                try:
                    # Get repository
                    result = await session.execute(
                        select(Repository).where(Repository.id == repository_id)
                    )
                    repo = result.scalar_one_or_none()
                
                    if not repo:
                        error_msg = f"Failed to sync repository: Repository with ID {repository_id} not found"
                        logger.error("repository_not_found", repository_id=repository_id, error=error_msg)
                        return {
                            "status": "error",
                            "error": error_msg,
                            "repository_id": repository_id
                        }
                
                    # Create or reuse job record (for retries)
                    # First, try to find job by celery_task_id
                    job_result = await session.execute(
                        select(Job).where(Job.celery_task_id == task.request.id)
                    )
                    job = job_result.scalar_one_or_none()
                
                    # If not found by task_id, check for pending retry job for this repository
                    # This handles race condition where monitor hasn't committed yet
                    if not job:
                        pending_result = await session.execute(
                            select(Job).where(
                                Job.repository_id == repository_id,
                                Job.job_type == "sync_repository",
                                Job.status == JobStatusEnum.PENDING
                            ).order_by(Job.updated_at.desc())
                        )
                        pending_job = pending_result.scalar_one_or_none()
                    
                        if pending_job:
                            # Found a pending retry job - use it and update task ID
                            logger.info(
                                "reusing_pending_retry_job",
                                job_id=pending_job.id,
                                old_task_id=pending_job.celery_task_id,
                                new_task_id=task.request.id
                            )
                            job = pending_job
                            job.celery_task_id = task.request.id
                
                    if not job:
                        # First attempt - create new job
                        job = Job(
                            repository_id=repository_id,
                            job_type="sync_repository",
                            status=JobStatusEnum.RUNNING,
                            celery_task_id=task.request.id,
                            started_at=datetime.utcnow()
                        )
                        session.add(job)
                    else:
                        # Retry attempt - update existing job
                        # CRITICAL: Distinguish between JobMonitor manual retry and Celery auto-retry
                        # - JobMonitor sets status=PENDING and already incremented retry_count
                        # - Celery auto-retry (self.retry()) keeps same task_id, needs increment
                        is_manual_retry = (job.status == JobStatusEnum.PENDING)
                    
                        job.status = JobStatusEnum.RUNNING
                        job.started_at = datetime.utcnow()
                        job.completed_at = None  # Clear old completion time
                        job.duration_seconds = None  # Clear old duration
                        job.error_message = None
                        job.error_traceback = None
                    
                        if not is_manual_retry:
                            # Celery automatic retry - increment counter
                            job.retry_count += 1
                            logger.info(
                                "celery_auto_retry_detected",
                                job_id=job.id,
                                retry_count=job.retry_count,
                                task_id=task.request.id
                            )
                        # else: JobMonitor already incremented retry_count, don't double-count
                
                    # Update repository status to cloning
                    repo.status = RepositoryStatusEnum.CLONING
                    await session.commit()
                    await session.refresh(job)
                    
                    # Store job_id and started_at in local variables to survive session.expunge_all()
                    # This is CRITICAL because expunge_all() on line 444 detaches all objects
                    job_id = job.id
                    job_started_at_ts = job.started_at
                
                    logger.info(
                        "repository_sync_job_created",
                        repository_id=repository_id,
                        job_id=job.id
                    )
                    await publisher.publish_log(repository_id, f"Repository sync job created (Job ID: {job.id})", details={"job_id": job.id})
                
                    # Initialize Pipeline Context
                    from src.workers.pipeline.context import PipelineContext, PipelineMetrics
                    
                    # Import all steps
                    from src.workers.pipeline.steps.clone_step import CloneStep
                    from src.workers.pipeline.steps.dotnet_restore_step import DotnetRestoreStep
                    from src.workers.pipeline.steps.roslyn_init_step import RoslynInitStep
                    from src.workers.pipeline.steps.discovery_step import DiscoveryStep
                    from src.workers.pipeline.steps.parsing_step import ParsingStep
                    from src.workers.pipeline.steps.api_extraction_step import ApiExtractionStep
                    from src.workers.pipeline.steps.reference_building_step import ReferenceBuildingStep
                    from src.workers.pipeline.steps.relationship_building_step import RelationshipBuildingStep
                    from src.workers.pipeline.steps.import_resolution_step import ImportResolutionStep
                    from src.workers.pipeline.steps.call_graph_step import CallGraphStep
                    from src.workers.pipeline.steps.dependency_extraction_step import DependencyExtractionStep
                    from src.workers.pipeline.steps.config_extraction_step import ConfigExtractionStep
                    from src.workers.pipeline.steps.ef_core_step import EfCoreExtractionStep
                    from src.workers.pipeline.steps.pattern_detection_step import PatternDetectionStep
                    from src.workers.pipeline.steps.combined_extraction_step import CombinedExtractionStep
                    from src.workers.pipeline.steps.embedding_step import EmbeddingGenerationStep
                    from src.workers.pipeline.steps.service_detection_step import ServiceDetectionStep
                    from src.workers.pipeline.steps.service_documentation_step import ServiceDocumentationStep

                    metrics_data = job.job_metadata or {}
                    hydrated_metrics = PipelineMetrics(
                        files_processed=metrics_data.get("files_processed", 0),
                        chunks_created=metrics_data.get("chunks_created", 0),
                        symbols_created=metrics_data.get("symbols_created", 0),
                        embeddings_generated=metrics_data.get("embeddings_generated", 0),
                        api_endpoints_count=metrics_data.get("api_endpoints_count", 0),
                        relationships_created=metrics_data.get("relationships_created", 0),
                        import_relationships_created=metrics_data.get("import_relationships_created", 0),
                        call_relationships_created=metrics_data.get("call_relationships_created", 0),
                        patterns_detected=metrics_data.get("patterns_detected", 0),
                        outgoing_calls_count=metrics_data.get("outgoing_calls_count", 0),
                        published_events_count=metrics_data.get("published_events_count", 0),
                        event_subscriptions_count=metrics_data.get("event_subscriptions_count", 0),
                        dependencies_found=metrics_data.get("dependencies_found", 0),
                        configs_found=metrics_data.get("configs_found", 0),
                        ef_entities_found=metrics_data.get("ef_entities_found", 0),
                        services_detected=metrics_data.get("services_detected", 0),
                        services_documented=metrics_data.get("services_documented", 0)
                    )

                    pipeline_ctx = PipelineContext(
                        repository_id=repository_id, 
                        session=session,
                        metrics=hydrated_metrics
                    )
                    pipeline_ctx.repository = repo
                    
                    # Define Pipeline Steps & Dependencies
                    steps = [
                        CloneStep(),
                        DotnetRestoreStep(),
                        RoslynInitStep(),
                        DiscoveryStep(),
                        ParsingStep(),
                        ApiExtractionStep(),
                        ReferenceBuildingStep(),
                        RelationshipBuildingStep(),
                        ImportResolutionStep(),
                        CallGraphStep(),
                        DependencyExtractionStep(),
                        ConfigExtractionStep(),
                        EfCoreExtractionStep(),
                        PatternDetectionStep(),
                        CombinedExtractionStep(),
                        EmbeddingGenerationStep(),
                        ServiceDetectionStep(),
                        ServiceDocumentationStep()
                    ]
                    
                    # Configure Dependencies (Fix 2: Dependency Validation)
                    # Core Build & Discovery
                    steps[1].depends_on = ["CloneStep"]          # DotnetRestore
                    steps[2].depends_on = ["DotnetRestoreStep"]   # RoslynInit
                    steps[3].depends_on = ["CloneStep"]          # Discovery
                    steps[4].depends_on = ["DiscoveryStep"]      # Parsing
                    
                    # Basic Extraction (depends on Parsing)
                    steps[5].depends_on = ["ParsingStep"]        # ApiExtraction
                    steps[6].depends_on = ["ParsingStep"]        # ReferenceBuilding
                    steps[7].depends_on = ["ParsingStep"]        # RelationshipBuilding
                    steps[8].depends_on = ["ParsingStep"]        # ImportResolution
                    steps[9].depends_on = ["ParsingStep"]        # CallGraph
                    steps[10].depends_on = ["ParsingStep"]       # DependencyExtraction
                    steps[11].depends_on = ["ParsingStep"]       # ConfigExtraction
                    steps[12].depends_on = ["ParsingStep"]       # EfCoreExtraction
                    steps[13].depends_on = ["ParsingStep"]       # PatternDetection
                    steps[14].depends_on = ["ParsingStep"]       # CombinedExtraction (Outgoing/Events)
                    
                    # Advanced Analysis
                    steps[15].depends_on = ["ParsingStep"]       # EmbeddingGeneration
                    steps[16].depends_on = ["RelationshipBuildingStep"] # ServiceDetection (needs graph)
                    steps[17].depends_on = ["ServiceDetectionStep"]     # ServiceDocumentation

                    # TRANSACTION MODEL: Fine-Grained Commits
                    # 
                    # The pipeline commits after EACH step for two reasons:
                    # 1. Memory: Large repos exhaust RAM if we hold uncommitted objects.
                    # 2. Resumability: Checkpoints enable partial progress recovery (Job.job_metadata).
                    #
                    # Trade-off: Partial failures leave incomplete data (e.g., symbols without embeddings).
                    # This is accepted because downstream steps are idempotent and can be retried.

                    # Execution Loop with Checkpoints
                    for step in steps:
                        # CRITICAL: Re-fetch job object at start of each iteration
                        # Steps like ParsingStep call session.expunge_all(), which detaches the job object.
                        # session.commit() also expires attributes.
                        # Always getting a fresh object ensures we don't hit MissingGreenlet or DetachedInstanceError.
                        if job_id:
                            job = await session.get(Job, job_id)
                            if not job:
                                logger.error("job_disappeared_during_sync", job_id=job_id)
                                break

                        # 1. Check Checkpoint
                        # We use job_metadata to store checkpoint state without new DB tables
                        current_metadata = job.job_metadata or {}
                        checkpoints = current_metadata.get("checkpoints", {})
                        
                        if checkpoints.get(step.name) == "completed":
                            logger.info(f"Skipping completed step: {step.name}")
                            pipeline_ctx.completed_steps.add(step.name)
                            continue
                        
                        # 2. Run Step
                        # The .run() method handles error logging and dependency validation
                        await step.run(pipeline_ctx)

                        # CRITICAL: Re-fetch job object AGAIN after step execution
                        # steps like ParsingStep call session.expunge_all() internally,
                        # which detaches the job object we fetched at the start of the loop.
                        if job_id:
                            job = await session.get(Job, job_id)
                            if not job:
                                logger.error("job_disappeared_after_step", job_id=job_id, step=step.name)
                                break
                        
                        # 3. Save Checkpoint
                        # Update local metadata dict
                        if not job.job_metadata: job.job_metadata = {}
                        # Refresh metadata from DB to avoid staleness? 
                        # Ideally we assume single writer per job.
                        
                        checkpoints = job.job_metadata.get("checkpoints", {})
                        checkpoints[step.name] = "completed"
                        job.job_metadata["checkpoints"] = checkpoints
                        
                        # Persist metrics progressively
                        job.job_metadata.update(pipeline_ctx.metrics.to_dict())
                        
                        # Force update on the object to ensure SQLAlchemy detects JSON change
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(job, "job_metadata")
                        
                        await session.commit()

                    # Final metrics sync
                    job.job_metadata.update(pipeline_ctx.metrics.to_dict())
                    
                    # Update repo size
                    size_stmt = select(func.sum(File.size_bytes)).where(File.repository_id == repository_id)
                    size_result = await session.execute(size_stmt)
                    repo.size_bytes = size_result.scalar() or 0
                    
                    # Preserve job_started_at logic
                    job_started_at = job_started_at_ts

                    # Step 4: Generate module summaries (Phase 2 - Optional, legacy task)
                    # We can keep this separate or wrap it in a step. For now, keeping as is.
                    modules_summarized = 0
                    try:
                        logger.info(
                            "module_summarization_started",
                            repository_id=repository_id
                        )
                        await publisher.publish_log(repository_id, "Generating module summaries...")
                        modules_summarized = await _generate_module_summaries(
                            session,
                            repository_id,
                            force_regenerate=False
                        )
                        
                        pipeline_ctx.metrics.modules_summarized = modules_summarized # Add to metrics
                        
                        logger.info(
                            "module_summarization_completed",
                            repository_id=repository_id,
                            modules_summarized=modules_summarized
                        )
                        await publisher.publish_log(repository_id, f"Module summarization completed. Summarized {modules_summarized} modules.", details={"modules_summarized": modules_summarized})
                    except Exception as e:
                        logger.error(
                            "module_summarization_failed",
                            repository_id=repository_id,
                            error=str(e),
                            traceback=traceback.format_exc()
                        )
                        await publisher.publish_log(repository_id, f"Module summarization failed: {str(e)}", level="ERROR")
                
                    # Step 5: Mark complete
                    # CRITICAL: Re-fetch repo object because it was detached by session.expunge_all()
                    repo = await session.get(Repository, repository_id)
                    repo.status = RepositoryStatusEnum.COMPLETED
                    repo.last_synced_at = datetime.utcnow()
                    repo.total_symbols = await _count_symbols(session, repository_id)
                 
                    # CRITICAL: Re-fetch job object because it was detached by session.expunge_all()
                    logger.debug("refetching_job_for_completion_update", job_id=job_id, repository_id=repository_id)
                    job_result = await session.execute(select(Job).where(Job.id == job_id))
                    job = job_result.scalar_one()
                    
                    job.status = JobStatusEnum.COMPLETED
                    job.completed_at = datetime.utcnow()
                    job.duration_seconds = int(
                        (job.completed_at - job_started_at_ts).total_seconds()
                    )
                    
                    # Final metadata update
                    final_metadata = job.job_metadata or {}
                    final_metadata.update(pipeline_ctx.metrics.to_dict())
                    job.job_metadata = final_metadata
                    flag_modified(job, "job_metadata")
                
                    # Log completion BEFORE commit to ensure job status is persisted even if logging fails
                    logger.info(
                        "repository_sync_completed",
                        repository_id=repository_id,
                        metrics=pipeline_ctx.metrics.to_dict(),
                        duration_seconds=job.duration_seconds
                    )
                    
                    # Try to publish success log, but don't let it prevent job completion
                    try:
                        await publisher.publish_log(repository_id, "Repository sync completed successfully!", level="SUCCESS", details={"duration": job.duration_seconds})
                    except Exception as publish_error:
                        logger.warning("failed_to_publish_completion_log", error=str(publish_error))
                    
                    # CRITICAL: Commit job status as COMPLETED. This must succeed.
                    try:
                        await session.commit()
                        logger.debug("job_completion_committed", job_id=job.id, repository_id=repository_id)
                    except Exception as commit_error:
                        # If commit fails, try to commit just the job status in isolation
                        logger.error(
                            "main_commit_failed_attempting_job_status_commit",
                            job_id=job.id,
                            repository_id=repository_id,
                            error=str(commit_error)
                        )
                        try:
                            # Rollback the failed transaction
                            await session.rollback()
                            # Fetch and update just the job
                            job_result = await session.execute(select(Job).where(Job.id == job.id))
                            job_to_update = job_result.scalar_one()
                            job_to_update.status = JobStatusEnum.COMPLETED
                            job_to_update.completed_at = job.completed_at
                            job_to_update.duration_seconds = job.duration_seconds
                            job_to_update.job_metadata = job.job_metadata
                            await session.commit()
                            logger.info("job_status_committed_in_recovery", job_id=job.id)
                        except Exception as recovery_error:
                            logger.error(
                                "failed_to_commit_job_status_in_recovery",
                                job_id=job.id,
                                error=str(recovery_error)
                            )
                            # Re-raise the original commit error
                            raise commit_error
                

                    # Trigger AI Enrichment (Axon v3.2)
                    try:
                        celery_app.send_task("src.workers.enrichment_worker.enrich_batch", args=[repository_id], countdown=10)
                        logger.info("enrichment_task_triggered", repository_id=repository_id)
                    except Exception as e:
                        logger.error("failed_to_trigger_enrichment", error=str(e))
                
                    return {
                        "status": "success",
                        "repository_id": repository_id,
                        "files_processed": pipeline_ctx.metrics.files_processed,
                        "chunks_created": pipeline_ctx.metrics.chunks_created,
                        "embeddings_generated": pipeline_ctx.metrics.embeddings_generated,
                        "api_endpoints_found": pipeline_ctx.metrics.api_endpoints_count,
                        "relationships_created": pipeline_ctx.metrics.relationships_created,
                        "import_relationships_created": pipeline_ctx.metrics.import_relationships_created,
                        "call_relationships_created": pipeline_ctx.metrics.call_relationships_created,
                        "patterns_detected": pipeline_ctx.metrics.patterns_detected,
                        "outgoing_calls_found": pipeline_ctx.metrics.outgoing_calls_count,
                        "published_events_found": pipeline_ctx.metrics.published_events_count,
                        "event_subscriptions_found": pipeline_ctx.metrics.event_subscriptions_count,
                        "dependencies_found": pipeline_ctx.metrics.dependencies_found,
                        "config_entries_found": pipeline_ctx.metrics.configs_found,
                        "duration_seconds": job.duration_seconds
                    }
                
                except Exception as e:
                    error_msg = f"Failed to sync repository: {str(e)}"
                    logger.error(
                        "repository_sync_failed",
                        repository_id=repository_id,
                        error=error_msg,
                        traceback=traceback.format_exc()
                    )
                    await publisher.publish_log(repository_id, f"Repository sync failed: {error_msg}", level="ERROR", details={"error": error_msg})
                
                    # Rollback immediately to clear any pending transaction state
                    # This must be done before accessing any object attributes
                    await session.rollback()
                
                    # Update repository and job status after rollback
                    # Note: After rollback, we need to refresh objects or work with cached values
                    if repo:
                        repo.status = RepositoryStatusEnum.FAILED
                
                    if job:
                        job.status = JobStatusEnum.FAILED
                        job.completed_at = datetime.utcnow()
                        job.error_message = error_msg
                        job.error_traceback = traceback.format_exc()
                    
                        # Use cached value from line 455 to avoid lazy loading after rollback
                        if job_started_at:
                            duration = (job.completed_at - job_started_at).total_seconds()
                            job.duration_seconds = int(duration)
                
                    # Commit failure state
                    try:
                        await session.commit()
                    except Exception as commit_error:
                        # If commit fails, log but don't mask the original error
                        logger.error(
                            "failed_to_commit_error_state",
                            repository_id=repository_id,
                            commit_error=str(commit_error),
                            original_error=error_msg
                        )
                        # Attempt rollback again
                        await session.rollback()
                
                    raise

    finally:
        # Critical: Clean up persistent processes (e.g., RoslynAnalyzer) before loop closes
        # This prevents "RuntimeError: Event loop is closed" in __del__ hooks
        try:

            await ParserFactory.cleanup()
        except Exception as e:
            logger.warning("parser_cleanup_failed", error=str(e))
            
        if publisher:
            await publisher.close()
            
        # Ensure session is closed
        if session:
            await session.close()
