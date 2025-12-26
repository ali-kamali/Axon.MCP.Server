from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, distinct, case

from src.database.models import (
    Repository, File, Symbol, OutgoingApiCall, 
    PublishedEvent, EventSubscription, Relation, ModuleSummary
)
from src.config.enums import SymbolKindEnum, RelationTypeEnum
from src.api.schemas.statistics import (
    OverviewStatistics, RepositoryStatistics, 
    SymbolDistribution, LanguageDistribution, RelationshipDistribution
)

class StatisticsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_overview_stats(self) -> OverviewStatistics:
        """Get global statistics overview."""
        
        # Basic counts
        total_repos = await self._get_count(select(func.count(Repository.id)))
        total_files = await self._get_count(select(func.count(File.id)))
        total_symbols = await self._get_count(select(func.count(Symbol.id)))
        
        # Specific symbol kinds
        total_endpoints = await self._get_count(
            select(func.count(Symbol.id)).where(Symbol.kind == SymbolKindEnum.ENDPOINT)
        )
        
        # Other entities
        total_calls = await self._get_count(select(func.count(OutgoingApiCall.id)))
        total_events = await self._get_count(select(func.count(PublishedEvent.id)))
        total_subs = await self._get_count(select(func.count(EventSubscription.id)))
        
        # Top languages
        lang_stmt = (
            select(
                File.language,
                func.count(File.id).label("count"),
                func.sum(File.size_bytes).label("size")
            )
            .group_by(File.language)
            .order_by(func.count(File.id).desc())
            .limit(10)
        )
        lang_result = await self.session.execute(lang_stmt)
        top_languages = [
            LanguageDistribution(
                language=row.language.value if hasattr(row.language, 'value') else str(row.language),
                file_count=row.count,
                size_bytes=int(row.size or 0)
            )
            for row in lang_result
        ]
        
        return OverviewStatistics(
            total_repositories=total_repos,
            total_files=total_files,
            total_symbols=total_symbols,
            total_endpoints=total_endpoints,
            total_outgoing_calls=total_calls,
            total_published_events=total_events,
            total_event_subscriptions=total_subs,
            top_languages=top_languages
        )

    async def get_repository_stats(self, repository_id: int) -> RepositoryStatistics:
        """Get statistics for a specific repository."""
        
        # Verify repo exists
        repo_result = await self.session.execute(
            select(Repository).where(Repository.id == repository_id)
        )
        repo = repo_result.scalar_one_or_none()
        if not repo:
            raise ValueError(f"Repository {repository_id} not found")

        # Basic counts
        total_files = await self._get_count(
            select(func.count(File.id)).where(File.repository_id == repository_id)
        )
        total_symbols = await self._get_count(
            select(func.count(Symbol.id))
            .join(File)
            .where(File.repository_id == repository_id)
        )
        total_endpoints = await self._get_count(
            select(func.count(Symbol.id))
            .join(File)
            .where(File.repository_id == repository_id, Symbol.kind == SymbolKindEnum.ENDPOINT)
        )
        total_calls = await self._get_count(
            select(func.count(OutgoingApiCall.id)).where(OutgoingApiCall.repository_id == repository_id)
        )
        total_events = await self._get_count(
            select(func.count(PublishedEvent.id)).where(PublishedEvent.repository_id == repository_id)
        )
        total_subs = await self._get_count(
            select(func.count(EventSubscription.id)).where(EventSubscription.repository_id == repository_id)
        )
        total_summaries = await self._get_count(
            select(func.count(ModuleSummary.id)).where(ModuleSummary.repository_id == repository_id)
        )
        
        # Quality Metrics
        # Files with 0 symbols
        files_no_symbols_stmt = (
            select(func.count(File.id))
            .outerjoin(Symbol, File.id == Symbol.file_id)
            .where(File.repository_id == repository_id)
            .group_by(File.id)
            .having(func.count(Symbol.id) == 0)
        )
        # The above query returns a row per file, we need to count those rows
        # Easier way: Count files where id NOT IN (select distinct file_id from symbols)
        files_with_symbols_subquery = (
            select(distinct(Symbol.file_id))
            .join(File)
            .where(File.repository_id == repository_id)
        )
        files_no_symbols = await self._get_count(
            select(func.count(File.id))
            .where(File.repository_id == repository_id)
            .where(File.id.not_in(files_with_symbols_subquery))
        )
        
        avg_symbols = total_symbols / total_files if total_files > 0 else 0.0
        
        # Distributions
        
        # 1. Symbol Distribution
        sym_dist_stmt = (
            select(Symbol.kind, func.count(Symbol.id))
            .join(File)
            .where(File.repository_id == repository_id)
            .group_by(Symbol.kind)
        )
        sym_dist_result = await self.session.execute(sym_dist_stmt)
        symbol_distribution = [
            SymbolDistribution(
                kind=row.kind.value if hasattr(row.kind, 'value') else str(row.kind),
                count=row.count
            )
            for row in sym_dist_result
        ]
        
        # 2. Language Distribution
        lang_dist_stmt = (
            select(
                File.language,
                func.count(File.id).label("count"),
                func.sum(File.size_bytes).label("size")
            )
            .where(File.repository_id == repository_id)
            .group_by(File.language)
        )
        lang_dist_result = await self.session.execute(lang_dist_stmt)
        language_distribution = [
            LanguageDistribution(
                language=row.language.value if hasattr(row.language, 'value') else str(row.language),
                file_count=row.count,
                size_bytes=int(row.size or 0)
            )
            for row in lang_dist_result
        ]
        
        # 3. Relationship Distribution
        # We need to join Relation -> Symbol (from) -> File -> Repository
        rel_dist_stmt = (
            select(Relation.relation_type, func.count(Relation.id))
            .join(Symbol, Relation.from_symbol_id == Symbol.id)
            .join(File, Symbol.file_id == File.id)
            .where(File.repository_id == repository_id)
            .group_by(Relation.relation_type)
        )
        rel_dist_result = await self.session.execute(rel_dist_stmt)
        relationship_distribution = [
            RelationshipDistribution(
                relation_type=row.relation_type.value if hasattr(row.relation_type, 'value') else str(row.relation_type),
                count=row.count
            )
            for row in rel_dist_result
        ]
        
        return RepositoryStatistics(
            repository_id=repo.id,
            repository_name=repo.name,
            total_files=total_files,
            total_symbols=total_symbols,
            total_endpoints=total_endpoints,
            total_outgoing_calls=total_calls,
            total_published_events=total_events,
            total_event_subscriptions=total_subs,
            total_module_summaries=total_summaries,
            files_with_no_symbols=files_no_symbols,
            avg_symbols_per_file=round(avg_symbols, 2),
            symbol_distribution=symbol_distribution,
            language_distribution=language_distribution,
            relationship_distribution=relationship_distribution
        )

    async def _get_count(self, stmt) -> int:
        """Helper to execute a count statement."""
        result = await self.session.execute(stmt)
        return result.scalar() or 0
