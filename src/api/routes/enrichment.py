"""
API routes for AI enrichment management.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.database.session import get_db_session as get_db
from src.database.models import Symbol, Repository
from src.workers.enrichment_worker import enrich_batch
from src.utils.logging_config import get_logger

router = APIRouter(prefix="/admin/enrichment", tags=["Enrichment"])
logger = get_logger(__name__)

@router.post("/trigger", status_code=202)
async def trigger_enrichment(
    repository_id: int = Query(..., description="Repository ID to enrich"),
    force: bool = Query(False, description="Whether to re-enrich existing symbols (not implemented yet for safety)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Trigger AI enrichment for a specific repository.
    """
    # Check repository exists
    repo = await db.get(Repository, repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Validate status
    if not force and repo.status != "COMPLETED":
        raise HTTPException(
            status_code=400, 
            detail=f"Repository must be fully synced before enrichment (current status: {repo.status}). Use force=True to override."
        )

    # Trigger task
    try:
        task = enrich_batch.delay(repository_id)
        return {
            "status": "triggered",
            "task_id": task.id,
            "repository_id": repository_id,
            "message": "Enrichment task started in background"
        }
    except Exception as e:
        logger.error(f"Failed to trigger enrichment task: {e}")
        raise HTTPException(status_code=500, detail="Failed to trigger background task")

@router.get("/stats")
async def get_enrichment_stats(
    repository_id: Optional[int] = Query(None, description="Filter by repository"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get statistics about AI enrichment coverage.
    """
    query = select(
        File.repository_id,
        func.count(Symbol.id).label("total_symbols"),
        func.count(Symbol.ai_enrichment).label("enriched_count")
    ).join(Symbol.file)
    
    if repository_id:
        query = query.where(File.repository_id == repository_id)
        
    query = query.group_by(File.repository_id)
    
    result = await db.execute(query)
    rows = result.all()
    
    stats = []
    for row in rows:
        stats.append({
            "repository_id": row.repository_id,
            "total_symbols": row.total_symbols,
            "enriched_count": row.enriched_count,
            "coverage_pct": round((row.enriched_count / row.total_symbols * 100), 2) if row.total_symbols > 0 else 0
        })
        
    return stats
