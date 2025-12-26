from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.database.models import (
    OutgoingApiCall, PublishedEvent, EventSubscription, 
    Symbol, File, ModuleSummary
)
from src.config.enums import SymbolKindEnum
from src.api.schemas.samples import (
    OutgoingApiCallSample, PublishedEventSample, EventSubscriptionSample,
    EndpointSample, ModuleSummarySample, RepositorySamples
)


class SampleService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_repository_samples(self, repository_id: int) -> RepositorySamples:
        """Get 5 random samples of each entity type for a repository."""
        
        # Fetch samples concurrently would be ideal, but for simplicity we'll do sequentially
        outgoing_calls = await self._get_outgoing_call_samples(repository_id)
        published_events = await self._get_published_event_samples(repository_id)
        event_subscriptions = await self._get_event_subscription_samples(repository_id)
        endpoints = await self._get_endpoint_samples(repository_id)
        module_summaries = await self._get_module_summary_samples(repository_id)
        
        return RepositorySamples(
            outgoing_calls=outgoing_calls,
            published_events=published_events,
            event_subscriptions=event_subscriptions,
            endpoints=endpoints,
            module_summaries=module_summaries
        )

    async def _get_outgoing_call_samples(self, repository_id: int) -> List[OutgoingApiCallSample]:
        """Get 5 random outgoing API call samples."""
        stmt = (
            select(OutgoingApiCall, File.path)
            .join(File, OutgoingApiCall.file_id == File.id)
            .where(OutgoingApiCall.repository_id == repository_id)
            .order_by(func.random())
            .limit(5)
        )
        result = await self.session.execute(stmt)
        
        samples = []
        for call, file_path in result:
            samples.append(OutgoingApiCallSample(
                id=call.id,
                http_method=call.http_method,
                url_pattern=call.url_pattern,
                http_client_library=call.http_client_library,
                line_number=call.line_number,
                file_path=file_path
            ))
        
        return samples

    async def _get_published_event_samples(self, repository_id: int) -> List[PublishedEventSample]:
        """Get 5 random published event samples."""
        stmt = (
            select(PublishedEvent, File.path)
            .join(File, PublishedEvent.file_id == File.id)
            .where(PublishedEvent.repository_id == repository_id)
            .order_by(func.random())
            .limit(5)
        )
        result = await self.session.execute(stmt)
        
        samples = []
        for event, file_path in result:
            samples.append(PublishedEventSample(
                id=event.id,
                event_type_name=event.event_type_name,
                messaging_library=event.messaging_library,
                line_number=event.line_number,
                file_path=file_path
            ))
        
        return samples

    async def _get_event_subscription_samples(self, repository_id: int) -> List[EventSubscriptionSample]:
        """Get 5 random event subscription samples."""
        stmt = (
            select(EventSubscription, File.path)
            .join(File, EventSubscription.file_id == File.id)
            .where(EventSubscription.repository_id == repository_id)
            .order_by(func.random())
            .limit(5)
        )
        result = await self.session.execute(stmt)
        
        samples = []
        for sub, file_path in result:
            samples.append(EventSubscriptionSample(
                id=sub.id,
                event_type_name=sub.event_type_name,
                handler_class_name=sub.handler_class_name,
                messaging_library=sub.messaging_library,
                line_number=sub.line_number,
                file_path=file_path
            ))
        
        return samples

    async def _get_endpoint_samples(self, repository_id: int) -> List[EndpointSample]:
        """Get 5 random endpoint samples."""
        stmt = (
            select(Symbol, File.path)
            .join(File, Symbol.file_id == File.id)
            .where(
                File.repository_id == repository_id,
                Symbol.kind == SymbolKindEnum.ENDPOINT
            )
            .order_by(func.random())
            .limit(5)
        )
        result = await self.session.execute(stmt)
        
        samples = []
        for symbol, file_path in result:
            samples.append(EndpointSample(
                id=symbol.id,
                name=symbol.name,
                signature=symbol.signature,
                documentation=symbol.documentation,
                line_number=symbol.start_line,
                file_path=file_path
            ))
        
        return samples

    async def _get_module_summary_samples(self, repository_id: int) -> List[ModuleSummarySample]:
        """Get 5 random module summary samples."""
        stmt = (
            select(ModuleSummary)
            .where(ModuleSummary.repository_id == repository_id)
            .order_by(func.random())
            .limit(5)
        )
        result = await self.session.execute(stmt)
        
        samples = []
        for summary in result.scalars():
            samples.append(ModuleSummarySample(
                id=summary.id,
                module_name=summary.module_name,
                module_path=summary.module_path,
                summary=summary.summary,
                file_count=summary.file_count,
                symbol_count=summary.symbol_count
            ))
        
        return samples
