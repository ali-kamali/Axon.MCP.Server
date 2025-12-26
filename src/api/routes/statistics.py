from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db_session
from src.api.schemas.statistics import OverviewStatistics, RepositoryStatistics
from src.api.services.statistics_service import StatisticsService
from src.api.auth import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])

@router.get("/statistics/overview", response_model=OverviewStatistics)
async def get_overview_statistics(
    session: AsyncSession = Depends(get_db_session),
) -> OverviewStatistics:
    """
    Get global statistics for the entire codebase.
    
    Returns counts of repositories, files, symbols, endpoints, and more.
    """
    service = StatisticsService(session)
    return await service.get_overview_stats()

@router.get("/statistics/repository/{repository_id}", response_model=RepositoryStatistics)
async def get_repository_statistics(
    repository_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> RepositoryStatistics:
    """
    Get detailed statistics for a specific repository.
    
    Includes:
    - Basic counts (files, symbols, endpoints)
    - Quality metrics (empty files, density)
    - Distributions (languages, symbol kinds, relationships)
    """
    service = StatisticsService(session)
    try:
        return await service.get_repository_stats(repository_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
