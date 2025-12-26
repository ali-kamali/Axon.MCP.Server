"""Symbol query helpers."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.symbols import RelationEdge, SymbolResponse, SymbolWithRelations
from src.database.models import File, Relation, Repository, Symbol


class SymbolService:
    """Provide read operations for symbols and relationships."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_symbol(self, symbol_id: int) -> Optional[SymbolResponse]:
        stmt: Select = (
            select(Symbol, File, Repository)
            .join(File, Symbol.file_id == File.id)
            .join(Repository, File.repository_id == Repository.id)
            .where(Symbol.id == symbol_id)
        )
        result = await self._session.execute(stmt)
        row = result.first()
        if row is None:
            return None

        symbol, file, repository = row
        
        # Ensure parameters is a dict or None, not a list
        parameters = symbol.parameters
        if isinstance(parameters, list):
            parameters = None if not parameters else {f"param_{i}": p for i, p in enumerate(parameters)}
        
        return SymbolResponse(
            id=symbol.id,
            file_id=file.id,
            repository_id=repository.id,
            language=symbol.language,
            kind=symbol.kind,
            access_modifier=symbol.access_modifier,
            name=symbol.name,
            fully_qualified_name=symbol.fully_qualified_name,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            signature=symbol.signature,
            documentation=symbol.documentation,
            parameters=parameters,
            return_type=symbol.return_type,
            parent_symbol_id=symbol.parent_symbol_id,
            created_at=symbol.created_at,
        )

    async def get_symbol_with_relations(self, symbol_id: int) -> Optional[SymbolWithRelations]:
        symbol = await self.get_symbol(symbol_id)
        if symbol is None:
            return None

        relations_stmt: Select = (
            select(Relation, Symbol)
            .join(Symbol, Relation.to_symbol_id == Symbol.id)
            .where(Relation.from_symbol_id == symbol_id)
        )
        result = await self._session.execute(relations_stmt)
        edges = []
        for relation, target in result.all():
            edges.append(
                RelationEdge(
                    id=relation.id,
                    relation_type=relation.relation_type,
                    to_symbol_id=relation.to_symbol_id,
                    to_symbol_name=target.name,
                    to_symbol_kind=target.kind,
                )
            )

        return SymbolWithRelations(**symbol.model_dump(), relations=edges)


