"""
System Context Generator.

This module provides functionality to generate a high-level system map and context
for the AI agent. It aggregates information from repository statistics, key modules,
database schema, and technology stack.
"""
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from sqlalchemy.orm import selectinload

from src.database.models import Repository, Symbol, File, Project
from src.config.enums import SymbolKindEnum
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

class SystemContextGenerator:
    """Generates high-level system context."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate_system_map(self, repository_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Generate a comprehensive system map.

        Args:
            repository_id: Optional repository ID to focus on. If None, generates global map.
        
        Returns:
            Dictionary containing system context.
        """
        context = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "repositories": [],
            "tech_stack": {},
            "key_modules": [],
            "database_schema": {}
        }

        # 1. Repositories & Tech Stack
        repos = await self._get_repositories(repository_id)
        context["repositories"] = repos
        context["tech_stack"] = await self._infer_tech_stack(repository_id)

        # 2. Key Modules (Top complexity/importance)
        context["key_modules"] = await self._get_key_modules(repository_id)

        # 3. Database Schema Overview (if inferable from code/schema)
        # For now, we'll placeholder this or extract generic info
        context["database_schema"] = await self._get_schema_overview()

        return context

    async def _get_repositories(self, repository_id: Optional[int]) -> List[Dict[str, Any]]:
        query = select(Repository)
        if repository_id:
            query = query.where(Repository.id == repository_id)
        
        result = await self.session.execute(query)
        repos = result.scalars().all()
        
        # Since we need to await async calls for each repo, we cannot do it inside list comp easily
        # or we need to fetch them first.
        repo_dicts = []
        for r in repos:
            repo_dicts.append({
                "id": r.id,
                "name": r.name,
                "description": r.description or "",
                "language": await self._get_repository_language(r.id)
            })
        
        return repo_dicts

    async def _infer_tech_stack(self, repository_id: Optional[int]) -> Dict[str, List[str]]:
        # This is a simplified inference. Real implementation would query Project/PackageJson tables
        tech_stack = {
            "languages": [],
            "frameworks": [],
            "databases": []
        }
        
        # Get languages
        query = select(File.language).distinct()
        if repository_id:
            query = query.where(File.repository_id == repository_id)
            
        result = await self.session.execute(query)
        tech_stack["languages"] = [str(r) for r in result.scalars().all() if r]

        # Get Frameworks from Projects (e.g. TargetFramework)
        p_query = select(Project.target_framework).distinct()
        if repository_id:
            p_query = p_query.where(Project.repository_id == repository_id)
        
        p_result = await self.session.execute(p_query)
        frameworks = [str(r) for r in p_result.scalars().all() if r]
        tech_stack["frameworks"] = frameworks

        return tech_stack

    async def _get_key_modules(self, repository_id: Optional[int]) -> List[Dict[str, Any]]:
        # Find high-level symbols (Classes/Modules) with high complexity or central roles
        # Phase 1: Simple complexity sort
        query = select(Symbol).options(selectinload(Symbol.file)).where(
            Symbol.kind.in_([SymbolKindEnum.CLASS, SymbolKindEnum.MODULE, SymbolKindEnum.NAMESPACE])
        ).limit(10)
        
        if repository_id:
            query = query.join(Symbol.file).where(File.repository_id == repository_id)
            
        result = await self.session.execute(query)
        symbols = result.scalars().all()
        
        return [{
            "name": s.name,
            "kind": str(s.kind),
            "file": s.file.path if s.file else "unknown",
            "description": self._safe_get_summary(s)
        } for s in symbols]
        
    def _safe_get_summary(self, symbol: Symbol) -> str:
        """Safely extract summary from potentially malformed JSON."""
        if not symbol.ai_enrichment:
            return symbol.documentation or ""
            
        if isinstance(symbol.ai_enrichment, dict):
            return symbol.ai_enrichment.get("functional_summary") or symbol.documentation or ""
            
        # Handle case where it might be string/list/etc due to other bugs
        return symbol.documentation or ""

    async def _get_schema_overview(self) -> Dict[str, Any]:
        """Attempt to extract schema info if EF Tools have populated it."""
        # Check for ef_entities table content (if migrated)
        # For now return placeholder
        return {"note": "Schema extraction pending implementation of EF/SQL parsers"}

    async def _get_repository_language(self, repository_id: int) -> str:
        """Determine primary language by file count."""
        try:
            query = (
                select(File.language, func.count(File.id).label("count"))
                .where(File.repository_id == repository_id)
                .group_by(File.language)
                .order_by(text("count DESC"))
                .limit(1)
            )
            result = await self.session.execute(query)
            row = result.first()
            return str(row[0].value) if row else "Unknown"
        except Exception as e:
            logger.error(f"failed_to_determine_language: {e}")
            return "Unknown"

