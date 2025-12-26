"""Search endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db_session, get_limiter
from src.api.schemas.search import SearchResult
from src.api.services.search_service import SearchService
from src.config.enums import LanguageEnum, SymbolKindEnum
from src.api.auth import get_current_user


router = APIRouter(dependencies=[Depends(get_current_user)])
limiter = get_limiter()


@router.get("/search", response_model=list[SearchResult])
@limiter.limit("30/minute")
async def search_code(
    request: Request,
    query: str = Query(..., min_length=2, max_length=200, description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results"),
    repository_id: Optional[int] = Query(None, description="Filter by repository"),
    language: Optional[LanguageEnum] = Query(None, description="Filter by language"),
    symbol_kind: Optional[SymbolKindEnum] = Query(None, description="Filter by symbol kind"),
    hybrid: bool = Query(True, description="Use hybrid search semantics"),
    session: AsyncSession = Depends(get_db_session),
) -> list[SearchResult]:
    """Search for symbols across indexed repositories."""

    search_service = SearchService(session)
    return await search_service.search(
        query,
        limit=limit,
        repository_id=repository_id,
        language=language,
        symbol_kind=symbol_kind,
        hybrid=hybrid,
    )


