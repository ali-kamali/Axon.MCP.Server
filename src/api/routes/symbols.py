"""Symbol inspection endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db_session
from src.api.schemas.symbols import SymbolResponse, SymbolWithRelations
from src.api.services.symbol_service import SymbolService
from src.api.auth import get_current_user


router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/symbols/{symbol_id}", response_model=SymbolResponse)
async def get_symbol(symbol_id: int, session: AsyncSession = Depends(get_db_session)) -> SymbolResponse:
    """Fetch metadata for a single symbol."""

    service = SymbolService(session)
    symbol = await service.get_symbol(symbol_id)
    if symbol is None:
        raise HTTPException(status_code=404, detail="Symbol not found")
    return symbol


@router.get("/symbols/{symbol_id}/relationships", response_model=SymbolWithRelations)
async def get_symbol_relations(
    symbol_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> SymbolWithRelations:
    """Fetch symbol details including outgoing relationships."""

    service = SymbolService(session)
    symbol = await service.get_symbol_with_relations(symbol_id)
    if symbol is None:
        raise HTTPException(status_code=404, detail="Symbol not found")
    return symbol


