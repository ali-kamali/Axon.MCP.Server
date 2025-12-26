from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, desc, or_
from sqlalchemy.orm import selectinload

from src.api.dependencies import get_db_session
from src.database.models import (
    Repository, Service, EfEntity, OutgoingApiCall, 
    PublishedEvent, EventSubscription, ApiEndpointLink, 
    EventLink, ConfigurationEntry, File
)
from src.database.session import AsyncSession
from src.api.schemas.analysis import (
    ServiceAnalysis, EfEntityAnalysis, IntegrationSummary,
    ConfigFinding, QualityAnalysis, QualityMetric
)
from src.api.auth import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])

@router.get("/repositories/{repository_id}/analysis/services", response_model=List[ServiceAnalysis])
async def get_repository_services(
    repository_id: int,
    db: AsyncSession = Depends(get_db_session)
):
    """Get detected services for a repository."""
    repo = await db.get(Repository, repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
        
    result = await db.execute(
        select(Service).where(Service.repository_id == repository_id).order_by(Service.name)
    )
    services = result.scalars().all()
    
    return [
        ServiceAnalysis(
            id=s.id,
            name=s.name,
            service_type=s.service_type,
            description=s.description,
            framework_version=s.framework_version,
            entry_points_count=len(s.entry_points) if s.entry_points else 0,
            documentation_path=s.documentation_path,
            created_at=s.created_at
        ) for s in services
    ]

@router.get("/repositories/{repository_id}/analysis/ef-entities", response_model=List[EfEntityAnalysis])
async def get_repository_ef_entities(
    repository_id: int,
    db: AsyncSession = Depends(get_db_session)
):
    """Get EF Core entities for a repository."""
    repo = await db.get(Repository, repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
        
    result = await db.execute(
        select(EfEntity).where(EfEntity.repository_id == repository_id).order_by(EfEntity.entity_name)
    )
    entities = result.scalars().all()
    
    return [
        EfEntityAnalysis(
            id=e.id,
            entity_name=e.entity_name,
            namespace=e.namespace,
            table_name=e.table_name,
            schema_name=e.schema_name,
            properties_count=len(e.properties) if e.properties else 0,
            relationships_count=len(e.relationships) if e.relationships else 0,
            has_primary_key=bool(e.primary_keys)
        ) for e in entities
    ]

@router.get("/repositories/{repository_id}/analysis/integrations", response_model=IntegrationSummary)
async def get_repository_integrations(
    repository_id: int,
    db: AsyncSession = Depends(get_db_session)
):
    """Get integration analysis summary for a repository."""
    repo = await db.get(Repository, repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    # Counts
    outgoing_count = await db.scalar(
        select(func.count(OutgoingApiCall.id)).where(OutgoingApiCall.repository_id == repository_id)
    )
    published_count = await db.scalar(
        select(func.count(PublishedEvent.id)).where(PublishedEvent.repository_id == repository_id)
    )
    subscription_count = await db.scalar(
        select(func.count(EventSubscription.id)).where(EventSubscription.repository_id == repository_id)
    )
    
    # Link counts
    endpoint_links_count = await db.scalar(
        select(func.count(ApiEndpointLink.id)).where(ApiEndpointLink.source_repository_id == repository_id)
    )
    event_links_count = await db.scalar(
        select(func.count(EventLink.id)).where(
            or_(
                EventLink.publisher_repository_id == repository_id,
                EventLink.subscriber_repository_id == repository_id
            )
        )
    )
    
    # Top targets (simplified analysis)
    # Group by URL pattern domain/prefix would be ideal, for now just returning raw patterns
    top_targets_res = await db.execute(
        select(OutgoingApiCall.url_pattern, func.count(OutgoingApiCall.id).label("count"))
        .where(OutgoingApiCall.repository_id == repository_id)
        .group_by(OutgoingApiCall.url_pattern)
        .order_by(desc("count"))
        .limit(5)
    )
    top_targets = [{"target": row[0], "count": row[1]} for row in top_targets_res.all()]
    
    # Top topics
    top_topics_res = await db.execute(
        select(PublishedEvent.event_type_name, func.count(PublishedEvent.id).label("count"))
        .where(PublishedEvent.repository_id == repository_id)
        .group_by(PublishedEvent.event_type_name)
        .order_by(desc("count"))
        .limit(5)
    )
    top_topics = [row[0] for row in top_topics_res.all()]
    
    return {
        "summary": {
            "outgoing_calls_count": outgoing_count or 0,
            "published_events_count": published_count or 0,
            "event_subscriptions_count": subscription_count or 0,
            "endpoint_links_count": endpoint_links_count or 0,
            "event_links_count": event_links_count or 0
        },
        "top_outgoing_targets": top_targets,
        "top_event_topics": top_topics
    }

@router.get("/repositories/{repository_id}/analysis/config-findings", response_model=List[ConfigFinding])
async def get_repository_config_findings(
    repository_id: int,
    db: AsyncSession = Depends(get_db_session)
):
    """Get configuration findings for a repository."""
    repo = await db.get(Repository, repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
        
    # Return secrets and interesting config keys
    result = await db.execute(
        select(ConfigurationEntry)
        .where(
            ConfigurationEntry.repository_id == repository_id,
            or_(
                ConfigurationEntry.is_secret == 1,
                ConfigurationEntry.config_key.ilike("%connection%"),
                ConfigurationEntry.config_key.ilike("%endpoint%"),
                ConfigurationEntry.config_key.ilike("%key%")
            )
        )
        .limit(50)
    )
    configs = result.scalars().all()
    
    return [
        ConfigFinding(
            id=c.id,
            config_key=c.config_key,
            config_value=c.config_value if not c.is_secret else "********",
            environment=c.environment,
            is_secret=bool(c.is_secret),
            file_path=c.file_path,
            line_number=c.line_number
        ) for c in configs
    ]

@router.get("/repositories/{repository_id}/analysis/quality-metrics", response_model=QualityAnalysis)
async def get_repository_quality_metrics(
    repository_id: int,
    db: AsyncSession = Depends(get_db_session)
):
    """Get code quality metrics for a repository."""
    repo = await db.get(Repository, repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    # Calculate files with no symbols (potential parsing issues or empty files)
    # Using a subquery approach or simply aggregating
    
    # For MVP, we'll perform a simpler calc
    total_files = repo.total_files
    
    # Files with no symbols
    files_no_symbols_count = await db.scalar(
        select(func.count(File.id))
        .outerjoin(File.symbols)
        .where(
            File.repository_id == repository_id,
            File.line_count > 0,
            # Ideally filter for source code extensions only
        )
        .group_by(File.id)
        .having(func.count(File.symbols) == 0)
    )
    
    # Calculate a simplified score
    metrics = []
    
    if total_files > 0:
        avg_lines = await db.scalar(
            select(func.avg(File.line_count)).where(File.repository_id == repository_id)
        )
        metrics.append(QualityMetric(
            category="Maintainability",
            metric_name="Avg Lines Per File",
            value=round(avg_lines or 0, 1),
            unit="lines",
            status="good" if (avg_lines or 0) < 300 else "warning"
        ))
        
        avg_symbols = await db.scalar(
            select(func.avg(File.size_bytes)).where(File.repository_id == repository_id)
        )
        metrics.append(QualityMetric(
            category="Complexity",
            metric_name="Avg File Size",
            value=round((avg_symbols or 0)/1024, 1),
            unit="KB",
            status="good"
        ))

    return QualityAnalysis(
        metrics=metrics,
        files_with_no_symbols=files_no_symbols_count or 0,
        files_with_errors=0, # Placeholder
        comment_ratio=0.0 # Placeholder
    )
