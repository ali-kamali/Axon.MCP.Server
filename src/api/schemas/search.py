"""Pydantic schemas for search endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from src.config.enums import LanguageEnum, SymbolKindEnum


class SearchResult(BaseModel):
    """Represents a single search match."""

    model_config = ConfigDict(from_attributes=True)

    # Primary identifiers (use these to get full content)
    symbol_id: int  # Use with GET /api/symbols/{symbol_id}
    file_id: int
    repository_id: int
    
    # Context information
    repository_name: str
    file_path: str
    language: LanguageEnum
    kind: SymbolKindEnum
    name: str
    fully_qualified_name: Optional[str] = None
    
    # Code details
    signature: Optional[str] = None
    documentation: Optional[str] = None
    code_snippet: Optional[str] = None  # Actual code preview (NEW)
    
    # Location
    start_line: int
    end_line: int
    
    # Search metadata
    score: float
    match_type: str = "keyword"  # "semantic", "keyword", or "hybrid"
    updated_at: datetime
    
    # Helpful URLs for getting full content (NEW)
    context_url: Optional[str] = None  # URL to get full symbol context


class SearchRequest(BaseModel):
    """Optional body payload for advanced search."""

    query: str
    limit: int = 20
    repository_id: Optional[int] = None
    language: Optional[LanguageEnum] = None
    symbol_kind: Optional[SymbolKindEnum] = None
    hybrid: bool = True


