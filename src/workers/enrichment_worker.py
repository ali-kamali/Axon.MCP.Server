"""
Celery tasks for AI enrichment of code symbols.
"""
import asyncio
from typing import List, Optional
from datetime import datetime
import json

from celery import shared_task
import sqlalchemy as sa
from sqlalchemy import select, update, and_
from sqlalchemy.orm import selectinload

from src.workers.celery_app import celery_app
from src.workers.utils import _run_with_engine_cleanup
from src.database.session import AsyncSessionLocal
from src.database.models import Symbol, Repository, File
from src.utils.logging_config import get_logger
from src.utils.llm_summarizer import LLMSummarizer
from src.config.settings import settings

logger = get_logger(__name__)

# Rate limit concurrent enrichment tasks to avoid hitting LLM limits too hard
# and to prevent overwhelming the worker
ENRICHMENT_BATCH_SIZE = 10
MAX_ENRICHMENT_ITERATIONS = 100

@celery_app.task(bind=True, name="src.workers.enrichment_worker.enrich_batch", max_retries=3)
def enrich_batch(self, repository_id: int, symbol_ids: Optional[List[int]] = None, iteration: int = 1):
    """
    Process a batch of symbols for AI enrichment.
    
    Args:
        repository_id: Repository ID
        symbol_ids: Optional list of specific symbol IDs to enrich. 
                   If None, finds symbols needing enrichment.
        iteration: Current iteration count for recursive batching
    """
    try:
        return asyncio.run(_run_with_engine_cleanup(_enrich_batch_async(self, repository_id, symbol_ids, iteration)))
    except Exception as e:
        logger.error(f"Enrichment batch failed: {e}")
        # Simple retry
        raise self.retry(exc=e, countdown=60)


async def _enrich_batch_async(task, repository_id: int, symbol_ids: Optional[List[int]] = None, iteration: int = 1):
    """Async implementation of batch enrichment."""
    logger.info("enrichment_batch_started", repository_id=repository_id, specific_symbols=len(symbol_ids) if symbol_ids else "ALL", iteration=iteration)
    
    
    try:
        llm = LLMSummarizer()
    except Exception as e:
        logger.error("failed_to_initialize_llm", repository_id=repository_id, error=str(e))
        return {
            "status": "failed",
            "enriched": 0,
            "failed": 0,
            "error": "LLM initialization failed"
        }
    enriched_count = 0
    failed_count = 0
    
    async with AsyncSessionLocal() as session:
        # Fetch symbols with file loaded
        query = select(Symbol).join(Symbol.file).options(selectinload(Symbol.file)).where(File.repository_id == repository_id)
        
        if symbol_ids:
            query = query.where(Symbol.id.in_(symbol_ids))
        else:
            # Find symbols missing enrichment AND have a valid name length
            query = query.where(
                and_(
                    Symbol.ai_enrichment.is_(None),
                    sa.func.length(Symbol.name) >= 3
                )
            )
            
        # Limit batch size if doing automatic selection and no specific IDs
        if not symbol_ids:
            # Locking: specific for PostgreSQL to avoid race conditions with multiple workers
            query = query.with_for_update(skip_locked=True).limit(ENRICHMENT_BATCH_SIZE)
            
        result = await session.execute(query)
        symbols = result.scalars().all()
        
        if not symbols:
            # Race Condition Fix:
            # slightly subtle: 'symbols' is empty might mean "all locked by others", not "all done".
            # We must verify if there are ANY pending symbols left for this repo, ignoring locks.
            
            # Count remaining unenriched symbols
            remaining_count = await session.scalar(
                select(sa.func.count(Symbol.id))
                .join(Symbol.file)
                .where(
                    File.repository_id == repository_id,
                    Symbol.ai_enrichment.is_(None),
                    sa.func.length(Symbol.name) >= 3
                )
            )
            
            if remaining_count == 0:
                logger.info("all_symbols_enriched", repository_id=repository_id)
                # NOW we can safely trigger aggregation
                if not symbol_ids:
                     _trigger_aggregation_task(repository_id)
            else:
                 logger.info("concurrent_workers_busy", repository_id=repository_id, remaining=remaining_count)
                 
            return {"status": "completed", "enriched": 0}

        logger.info("processing_enrichment_batch", count=len(symbols))
        
        # Prepare coroutines for parallel LLM execution
        enrichment_coroutines = []
        valid_symbols = []

        for symbol in symbols:
            # 1. Orphan Check
            if not symbol.file:
                logger.warning("skipping_orphaned_symbol", symbol_id=symbol.id)
                failed_count += 1
                continue
            
            valid_symbols.append(symbol)
            file_path = symbol.file.path  # Already confirmed symbol.file exists above
            
            # Create a coroutine for each valid symbol
            enrichment_coroutines.append(
                _generate_enrichment_for_symbol_data(
                    llm, 
                    {
                        "id": symbol.id,
                        "name": symbol.name,
                        "kind": symbol.kind,
                        "signature": symbol.signature,
                        "documentation": symbol.documentation,
                        "file_path": file_path
                    }
                )
            )
            
        if enrichment_coroutines:
            logger.info("executing_llm_requests_parallel", count=len(enrichment_coroutines))
            
            # Run all LLM requests in parallel with timeout protection
            # Individual requests have llm_request_timeout, but we add batch-level protection
            batch_timeout = settings.llm_request_timeout * 2  # 2x individual timeout for safety
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*enrichment_coroutines, return_exceptions=True),
                    timeout=batch_timeout
                )
            except asyncio.TimeoutError:
                logger.error(
                    "batch_timeout_exceeded",
                    repository_id=repository_id,
                    timeout_seconds=batch_timeout,
                    symbol_count=len(enrichment_coroutines)
                )
                # Mark all as failed
                failed_count += len(enrichment_coroutines)
                # Continue to next batch logic
                results = []  # Empty results to skip the result processing loop
            
            # Validate results count matches expectations
            if results and len(results) != len(valid_symbols):
                logger.error(
                    "result_count_mismatch",
                    expected=len(valid_symbols),
                    received=len(results)
                )
                # This should never happen with asyncio.gather, but defensive programming
                failed_count += len(valid_symbols)
                results = []
            
            # Process results sequentially to update DB
            for symbol, result in zip(valid_symbols, results):
                try:
                    if isinstance(result, Exception):
                        logger.error("symbol_enrichment_task_failed", symbol_id=symbol.id, error=str(result))
                        failed_count += 1
                        continue
                        
                    enrichment = result
                    
                    if enrichment:
                        symbol.ai_enrichment = enrichment
                        # Commit per symbol to keep the original safety
                        await session.commit()
                        enriched_count += 1
                        logger.debug("symbol_enriched_successfully", symbol_id=symbol.id, symbol_name=symbol.name, kind=symbol.kind)
                    else:
                        logger.warning("symbol_enrichment_returned_none", symbol_id=symbol.id, symbol_name=symbol.name)
                        failed_count += 1
                        
                except Exception as e:
                    await session.rollback()
                    logger.error("symbol_enrichment_save_failed", symbol_id=symbol.id, error=str(e))
                    failed_count += 1
        
        # If we were processing automatic batch and found items, 
        # assume there might be more and trigger next batch recursively
        if not symbol_ids and len(symbols) == ENRICHMENT_BATCH_SIZE:
             if iteration < MAX_ENRICHMENT_ITERATIONS:
                 # Trigger next batch via name to avoid circular import issues
                 logger.info("triggering_next_batch", repository_id=repository_id, next_iteration=iteration + 1)
                 celery_app.send_task(
                     "src.workers.enrichment_worker.enrich_batch",
                     args=[repository_id],
                     kwargs={"iteration": iteration + 1},
                     countdown=2
                 )
             else:
                 logger.warning("max_enrichment_iterations_reached", repository_id=repository_id)
                 # Even if max reached, we should probably aggregate what we have
                 _trigger_aggregation_task(repository_id)
        
        # We finished the last batch (queue drained)
        elif not symbol_ids:
             _trigger_aggregation_task(repository_id)
             
    # Log completion summary
    logger.info(
        "enrichment_batch_completed",
        repository_id=repository_id,
        enriched=enriched_count,
        failed=failed_count,
        iteration=iteration
    )
             
    return {
        "status": "completed", 
        "enriched": enriched_count, 
        "failed": failed_count,
        "repository_id": repository_id
    }

def _trigger_aggregation_task(repository_id: int):
    """Helper to trigger repository aggregation."""
    try:
        celery_app.send_task(
            "src.workers.aggregation_worker.aggregate_repository_summary",
            args=[repository_id],
            countdown=5
        )
        logger.info("aggregation_task_triggered", repository_id=repository_id)
    except Exception as e:
        logger.error("failed_to_trigger_aggregation", repository_id=repository_id, error=str(e))


async def _generate_enrichment_for_symbol_data(llm: LLMSummarizer, symbol_data: dict) -> Optional[dict]:
    """Generate business context enrichment from extracted symbol data."""
    
    # Extract data
    symbol_name = symbol_data["name"]
    symbol_id = symbol_data["id"]
    file_path = symbol_data["file_path"]
    
    # Skip trivial symbols
    if not symbol_name or len(symbol_name) < 3:
        logger.info("skipping_trivial_symbol", symbol_id=symbol_id, symbol_name=symbol_name)
        return None
        
    prompt = f"""
Analyze the following code symbol and provide business context:

Symbol: {symbol_name}
Kind: {symbol_data['kind']}
File: {file_path}
Signature: {symbol_data['signature'] or 'N/A'}
DocString: {symbol_data['documentation'] or 'None'}

Context:
This symbol is part of a larger codebase. Based on its name and signature, explain its likely business purpose and responsibility.

Return JSON with keys:
- business_purpose: What business function this supports
- domain_concept: The domain entity or concept it represents
- functional_summary: One sentence technical summary
"""
    # Use the new async method
    logger.debug("requesting_llm_enrichment", symbol_id=symbol_id, symbol_name=symbol_name, file_path=file_path)
    response_text = await llm.summarize_async(prompt)
    
    if not response_text:
        logger.error("llm_response_empty", symbol_id=symbol_id, symbol_name=symbol_name)
        return None
        
    try:
        # clean code fences
        cleaned_text = response_text
        if "```json" in cleaned_text:
            cleaned_text = cleaned_text.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned_text:
            cleaned_text = cleaned_text.split("```")[1].split("```")[0].strip()
            
        data = json.loads(cleaned_text)
        
        # Quality Check: Ensure fields are not empty
        # Reduced threshold from 10 to 5 to accept more valid responses
        if not data.get("functional_summary") or len(data["functional_summary"]) < 5:
             raise ValueError("Functional summary too short")
             
        # NOTE: Removed "AI Analysis" check as it rejected the fallback response
        # The fallback is intentionally generic when JSON parsing fails
             
        return data
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        # Fallback to saving as text
        logger.warning(
            "failed_to_parse_llm_response",
            symbol_id=symbol_id,
            symbol_name=symbol_name,
            error=str(e),
            response_preview=response_text[:200]
        )
        return {
            "functional_summary": response_text[:1000],  # Increased from 500 to preserve more context
            "business_purpose": "AI Analysis (Unstructured)",
            "raw_response": response_text[:2000]  # Increased from 1000 for debugging
        }
