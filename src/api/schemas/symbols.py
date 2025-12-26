"""Pydantic schemas for symbol endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from src.config.enums import AccessModifierEnum, LanguageEnum, RelationTypeEnum, SymbolKindEnum


class RelationEdge(BaseModel):
    """Represents a relationship between symbols."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    relation_type: RelationTypeEnum
    to_symbol_id: int
    to_symbol_name: str
    to_symbol_kind: SymbolKindEnum


class SymbolResponse(BaseModel):
    """Detailed symbol information."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    file_id: int
    repository_id: int
    language: LanguageEnum
    kind: SymbolKindEnum
    access_modifier: Optional[AccessModifierEnum] = None
    name: str
    fully_qualified_name: Optional[str] = None
    start_line: int
    end_line: int
    signature: Optional[str] = None
    documentation: Optional[str] = None
    parameters: Optional[dict] = None
    return_type: Optional[str] = None
    parent_symbol_id: Optional[int] = None
    created_at: datetime


class SymbolWithRelations(SymbolResponse):
    """Symbol response including relationship edges."""

    relations: List[RelationEdge] = []


