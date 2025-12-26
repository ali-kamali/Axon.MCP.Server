"""
Extractor for event publishing and subscriptions from code.

Supports multiple event patterns:
1. Custom Event Classes: Classes inheriting from Event or IIntegrationEvent
2. QueueEvent: .QueueEvent() method for queuing events on aggregates
3. PublishAggregatedEvents: Publishing queued events from aggregate roots
4. MassTransit: Publish, PublishBatch, Send, Request patterns
5. IConsumer: Event subscription handlers
"""

from typing import List, Dict, Any, Optional
import re
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Symbol, File, PublishedEvent, EventSubscription, Repository
from src.config.enums import SymbolKindEnum, LanguageEnum
from src.utils.logging_config import get_logger
from src.parsers.javascript_parser import JavaScriptParser

logger = get_logger(__name__)


class EventExtractor:
    """Extracts event publishing and subscriptions from parsed code."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.js_parser = JavaScriptParser()
    
    async def extract_events(self, repository_id: int) -> int:
        """
        Extract events from a repository.
        
        Args:
            repository_id: Repository ID
            
        Returns:
            Number of events/subscriptions extracted
        """
        # This method is a placeholder for the main logic if we were iterating here
        # But we'll likely call extract_from_file from the main task loop
        return 0

    async def extract_from_file(self, file: File, repo_path: Any, content: Optional[str] = None) -> Dict[str, List[Any]]:
        """
        Extract events from a single file.
        
        Args:
            file: File model
            repo_path: Path to repository root
            content: Optional file content (if already read)
            
        Returns:
            Dict with 'published' and 'subscribed' lists
        """
        logger.debug(
            "event_extraction_started",
            file_id=file.id,
            file_path=file.path,
            language=file.language
        )
        
        result = {
            'published': [],
            'subscribed': []
        }
        
        file_path = repo_path / file.path
        
        try:
            if content is None:
                if not file_path.exists():
                    return result
                content = file_path.read_text(encoding='utf-8-sig', errors='ignore')
            
            if file.language == LanguageEnum.CSHARP:
                events = await self._extract_csharp_events(content, file)
                result['published'].extend(events['published'])
                result['subscribed'].extend(events['subscribed'])
            elif file.language in [LanguageEnum.JAVASCRIPT, LanguageEnum.TYPESCRIPT]:
                events = self._extract_js_events(content, file)
                result['published'].extend(events['published'])
                result['subscribed'].extend(events['subscribed'])
                
        except Exception as e:
            logger.error(f"Error extracting events from {file.path}: {e}")
            
        return result

    async def _extract_csharp_events(self, content: str, file: File) -> Dict[str, List[Any]]:
        """Extract events from C# code (MassTransit, custom Event classes, and QueueEvent)."""
        published = []
        subscribed = []
        
        # 1. Detect Event Class Definitions
        # Classes that inherit from Event or IIntegrationEvent
        # Example: public class SendMessage : Event, IIntegrationEvent
        event_class_pattern = r'class\s+(\w+)\s*:\s*(?:[^{]*\b(?:Event|IIntegrationEvent)\b[^{]*)'
        
        for match in re.finditer(event_class_pattern, content):
            event_type = match.group(1)
            line_number = content[:match.start()].count('\n') + 1
            
            logger.debug(
                "event_class_definition_found",
                event_type=event_type,
                file_id=file.id,
                line_number=line_number
            )
            
            # Note: Event class definitions are not "published" events
            # They are event type definitions that can be used elsewhere
            # We could store these separately or skip them
            # For now, we'll skip storing class definitions and only track actual publishing
        
        # 2. Detect QueueEvent Publishing
        # Example: physicianReport.QueueEvent(CreateMessage(physicianReport.PhysicianId))
        # Pattern matches: .QueueEvent( with optional arguments
        queue_event_pattern = r'\.QueueEvent\s*\('
        
        for match in re.finditer(queue_event_pattern, content):
            line_number = content[:match.start()].count('\n') + 1
            
            # Try to extract the event type from the argument
            # Look for patterns like: new EventType, CreateEventType(), variable name
            line_start = content.rfind('\n', 0, match.start()) + 1
            line_end = content.find('\n', match.end())
            if line_end == -1:
                line_end = len(content)
            line_content = content[line_start:line_end]
            
            # Try to find event type in the QueueEvent call
            # Pattern 1: .QueueEvent(new EventType
            new_match = re.search(r'QueueEvent\s*\(\s*new\s+(\w+)', line_content)
            # Pattern 2: .QueueEvent(CreateSomething(...)) or .QueueEvent(variableName)
            method_or_var_match = re.search(r'QueueEvent\s*\(\s*(\w+)', line_content)
            
            event_type = None
            if new_match:
                event_type = new_match.group(1)
            elif method_or_var_match:
                # Use the method/variable name as a hint
                event_type = method_or_var_match.group(1)
            else:
                event_type = "UnknownEvent"
            
            published.append(PublishedEvent(
                repository_id=file.repository_id,
                file_id=file.id,
                event_type_name=event_type,
                messaging_library="QueueEvent",
                line_number=line_number
            ))
            
            logger.debug(
                "queue_event_found",
                event_type=event_type,
                file_id=file.id,
                line_number=line_number
            )
        
        # 3. Detect MassTransit Publishing
        # await _publishEndpoint.Publish<UserCreated>(new { ... })
        # await bus.Publish(new UserCreated { ... })
        
        # Regex for Publish<T> or Publish(new T)
        # Matches: .Publish<UserCreated>
        publish_generic_pattern = r'\.Publish\s*<([^>]+)>'
        # Matches: .Publish(new UserCreated
        publish_new_pattern = r'\.Publish\s*\(\s*new\s+([^\s{(]+)'
        
        # Batch Publish
        # .PublishBatch<T>
        publish_batch_pattern = r'\.PublishBatch\s*<([^>]+)>'
        
        # Send (Direct)
        # .Send<T>
        send_pattern = r'\.Send\s*<([^>]+)>'
        # .Send(new T)
        send_new_pattern = r'\.Send\s*\(\s*new\s+([^\s{(]+)'
        
        # Request/Response
        # .Request<T>
        request_pattern = r'\.Request\s*<([^>]+)>'
        
        patterns = [
            (publish_generic_pattern, "MassTransit.Publish"),
            (publish_new_pattern, "MassTransit.Publish"),
            (publish_batch_pattern, "MassTransit.PublishBatch"),
            (send_pattern, "MassTransit.Send"),
            (send_new_pattern, "MassTransit.Send"),
            (request_pattern, "MassTransit.Request"),
        ]
        
        for pattern, library_suffix in patterns:
            for match in re.finditer(pattern, content):
                event_type = match.group(1)
                line_number = content[:match.start()].count('\n') + 1
                published.append(PublishedEvent(
                    repository_id=file.repository_id,
                    file_id=file.id,
                    event_type_name=event_type,
                    messaging_library=library_suffix,
                    line_number=line_number
                ))
        
        # 4. Detect PublishAggregatedEvents
        # Example: await PublishAggregatedEvents(physicianReport)
        # This pattern publishes events that were queued on an aggregate root
        publish_aggregated_pattern = r'\bPublishAggregatedEvents\s*\('
        
        for match in re.finditer(publish_aggregated_pattern, content):
            line_number = content[:match.start()].count('\n') + 1
            
            # Try to extract the aggregate variable name
            line_start = content.rfind('\n', 0, match.start()) + 1
            line_end = content.find('\n', match.end())
            if line_end == -1:
                line_end = len(content)
            line_content = content[line_start:line_end]
            
            # Extract the parameter (aggregate variable)
            param_match = re.search(r'PublishAggregatedEvents\s*\(\s*(\w+)', line_content)
            aggregate_name = param_match.group(1) if param_match else "UnknownAggregate"
            
            published.append(PublishedEvent(
                repository_id=file.repository_id,
                file_id=file.id,
                event_type_name=f"AggregatedEvents({aggregate_name})",
                messaging_library="PublishAggregatedEvents",
                line_number=line_number
            ))
            
            logger.debug(
                "publish_aggregated_events_found",
                aggregate_name=aggregate_name,
                file_id=file.id,
                line_number=line_number
            )

        # 2. Detect Subscribing (Consumers)
        # public class UserCreatedConsumer : IConsumer<UserCreated>
        
        # Pre-compute all class definitions once to avoid O(n²) performance issue
        # This prevents re-running regex on increasingly large substrings for each match
        all_class_matches = [(m.start(), m.group(1)) for m in re.finditer(r'class\s+(\w+)', content)]
        
        consumer_pattern = r':\s*IConsumer\s*<([^>]+)>'
        
        for match in re.finditer(consumer_pattern, content):
            event_type = match.group(1)
            line_number = content[:match.start()].count('\n') + 1
            
            # Find the last class definition before this match
            handler_name = "UnknownConsumer"
            for class_pos, class_name in all_class_matches:
                if class_pos < match.start():
                    handler_name = class_name
                else:
                    break
            
            # Try to find the Symbol for this handler class (best effort)
            # Flush pending writes to avoid deadlocks when querying
            try:
                await self.session.flush()
            except Exception as flush_error:
                logger.warning(
                    "session_flush_failed_before_symbol_query",
                    file_id=file.id,
                    handler_name=handler_name,
                    error=str(flush_error)
                )
            
            symbol_result = await self.session.execute(
                select(Symbol)
                .where(
                    Symbol.file_id == file.id,
                    Symbol.kind == SymbolKindEnum.CLASS,
                    Symbol.name == handler_name
                )
            )
            handler_symbol = symbol_result.scalar_one_or_none()
            
            # Create EventSubscription regardless of whether Symbol was found
            # symbol_id will be None if Symbol doesn't exist
            subscribed.append(EventSubscription(
                symbol_id=handler_symbol.id if handler_symbol else None,
                repository_id=file.repository_id,
                file_id=file.id,
                event_type_name=event_type,
                messaging_library="MassTransit",
                handler_class_name=handler_name,
                line_number=line_number
            ))
            
            if handler_symbol:
                logger.debug(
                    "event_subscription_created_with_symbol",
                    handler_class_name=handler_name,
                    symbol_id=handler_symbol.id,
                    event_type=event_type
                )
            else:
                logger.info(
                    "event_subscription_created_without_symbol",
                    handler_class_name=handler_name,
                    file_id=file.id,
                    event_type=event_type
                )
            
        return {
            'published': published,
            'subscribed': subscribed
        }

    def _extract_js_events(self, content: str, file: File) -> Dict[str, List[Any]]:
        """Extract events from JS/TS code using AST parser."""
        published = []
        subscribed = []
        
        try:
            # Parse code using JavaScriptParser which now includes event extraction
            parse_result = self.js_parser.parse(content, file.path)
            
            for event in parse_result.events:
                event_type = event.get('type')
                
                if event_type == 'publish':
                    published.append(PublishedEvent(
                        repository_id=file.repository_id,
                        file_id=file.id,
                        event_type_name=event.get('event_type_name', 'UnknownEvent'),
                        messaging_library=event.get('messaging_library', 'unknown'),
                        topic_name=event.get('topic_name'),
                        routing_key=event.get('routing_key'),
                        line_number=event.get('line_number', 0),
                        event_metadata=event.get('event_metadata')
                    ))
                elif event_type == 'subscribe':
                    subscribed.append(EventSubscription(
                        repository_id=file.repository_id,
                        file_id=file.id,
                        event_type_name=event.get('event_type_name', 'UnknownEvent'),
                        messaging_library=event.get('messaging_library', 'unknown'),
                        queue_name=event.get('queue_name'),
                        line_number=event.get('line_number', 0),
                        handler_metadata=event.get('event_metadata')
                    ))
                    
        except Exception as e:
            logger.error(f"Error parsing JS events in {file.path}: {e}")
            
        return {
            'published': published,
            'subscribed': subscribed
        }
