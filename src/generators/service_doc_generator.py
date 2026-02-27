import asyncio
import logging
import os
import re
from pathlib import Path
from datetime import datetime, UTC
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from src.database.models import (
    Service, Symbol, OutgoingApiCall, PublishedEvent, 
    EventSubscription, Dependency, ProjectReference
)
from src.utils.llm_summarizer import LLMSummarizer
from src.config.enums import SymbolKindEnum
from src.config.settings import get_settings

logger = logging.getLogger(__name__)

# Constants
MAX_CONTROLLERS_FOR_LLM = 10
MAX_METHODS_PER_CONTROLLER = 20
MAX_DEPENDENCIES_DISPLAY = 20
MAX_PROJECT_REFS_DISPLAY = 10
MAX_EXTERNAL_CALLS_DISPLAY = 10
MAX_EVENTS_DISPLAY = 10

class ServiceDocGenerator:
    """
    Generates comprehensive markdown documentation for a Service.
    Uses LLM to generate descriptions and provides complete technical information.
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.llm = LLMSummarizer()
        
    async def generate_service_doc(self, service: Service) -> str:
        """
        Generates the complete markdown documentation for a service.
        """
        logger.info(f"Generating documentation for service: {service.name}")
        
        # 1. Gather Data (optimized with eager loading)
        service_data = await self._gather_service_data(service)
        
        # 2. Generate Content Sections
        responsibility = await self._generate_responsibility(service, service_data['controllers'])
        overview_section = self._generate_overview(service)
        architecture_section = self._generate_architecture_section(
            self._extract_architecture_patterns(service)
        )
        api_section = self._generate_api_section(
            service_data['controllers'], 
            service_data['controller_methods']
        )
        dependency_section = self._generate_dependency_section(
            service_data['dependencies'],
            service_data['project_references'],
            service_data['external_calls']
        )
        event_section = self._generate_event_section(
            service_data['events_published'],
            service_data['events_subscribed']
        )
        technical_section = self._generate_technical_section(service)
        
        # 3. Assemble Markdown
        markdown = f"""# {service.name}

## Overview
{overview_section}

## Responsibility
{responsibility}

## Architecture
{architecture_section}

## API Endpoints
{api_section}

## Dependencies
{dependency_section}

## Events & Messaging
{event_section}

## Technical Details
{technical_section}

---
*Documentation generated on {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC*
"""
        return markdown

    async def _gather_service_data(self, service: Service) -> Dict[str, Any]:
        """
        Gather all service data with optimized queries.
        Uses eager loading and batching to minimize DB roundtrips.
        """
        from sqlalchemy import cast, String
        
        # Query 1: Get controllers with their methods in one go
        controllers_result = await self.session.execute(
            select(Symbol)
            .options(selectinload(Symbol.children))
            .filter(
                Symbol.service_id == service.id,
                Symbol.kind == SymbolKindEnum.CLASS,
                (Symbol.name.like("%Controller")) | 
                (cast(Symbol.attributes, String).like("%ApiController%"))
            )
        )
        controllers = controllers_result.scalars().all()
        
        # Query 2: Get controller methods
        # Note: Some methods have NULL parent_symbol_id but valid parent_name (Roslyn parser bug)
        # We match by BOTH parent_symbol_id (FK) AND parent_name (FQN string) to capture all methods
        controller_ids = [c.id for c in controllers]
        controller_fqns = [c.fully_qualified_name for c in controllers]
        controller_methods = {}
        
        if controller_ids:
            from sqlalchemy import or_
            methods_result = await self.session.execute(
                select(Symbol).filter(
                    Symbol.service_id == service.id,
                    Symbol.kind == SymbolKindEnum.METHOD,
                    or_(
                        Symbol.parent_symbol_id.in_(controller_ids),  # Match by FK
                        Symbol.parent_name.in_(controller_fqns)       # Match by FQN string (fallback for NULL FK)
                    )
                )
            )
            methods = methods_result.scalars().all()
            
            # Group by parent's fully_qualified_name (to match lookup in _generate_api_section)
            for method in methods:
                # Match by parent_symbol_id first (if set), otherwise by parent_name
                if method.parent_symbol_id:
                    parent_controller = next((c for c in controllers if c.id == method.parent_symbol_id), None)
                else:
                    # Fallback: match by parent_name FQN
                    parent_controller = next((c for c in controllers if c.fully_qualified_name == method.parent_name), None)
                
                if parent_controller:
                    parent_fqn = parent_controller.fully_qualified_name
                    if parent_fqn not in controller_methods:
                        controller_methods[parent_fqn] = []
                    controller_methods[parent_fqn].append(method)
        
        # Query 3: Dependencies (repository-wide)
        deps_result = await self.session.execute(
            select(Dependency).filter(
                Dependency.repository_id == service.repository_id
            )
        )
        dependencies = deps_result.scalars().all()
        
        # Query 4: Project References (for this service)
        refs_result = await self.session.execute(
            select(ProjectReference).filter(
                ProjectReference.repository_id == service.repository_id,
                ProjectReference.source_project_path.like(f"%{service.name}%")
            )
        )
        project_references = refs_result.scalars().all()
        
        # Query 5: External calls, published events, subscribed events (one query with joins)
        # Get all symbols for this service first
        service_symbols_result = await self.session.execute(
            select(Symbol.id).filter(Symbol.service_id == service.id)
        )
        service_symbol_ids = [row[0] for row in service_symbols_result.all()]
        
        external_calls = []
        events_published = []
        events_subscribed = []
        
        if service_symbol_ids:
            # External calls
            calls_result = await self.session.execute(
                select(OutgoingApiCall).filter(
                    OutgoingApiCall.symbol_id.in_(service_symbol_ids)
                )
            )
            external_calls = calls_result.scalars().all()
            
            # Published events
            pub_events_result = await self.session.execute(
                select(PublishedEvent).filter(
                    PublishedEvent.symbol_id.in_(service_symbol_ids)
                )
            )
            events_published = pub_events_result.scalars().all()
            
            # Subscribed events
            sub_events_result = await self.session.execute(
                select(EventSubscription).filter(
                    EventSubscription.symbol_id.in_(service_symbol_ids)
                )
            )
            events_subscribed = sub_events_result.scalars().all()
        
        return {
            'controllers': controllers,
            'controller_methods': controller_methods,
            'dependencies': dependencies,
            'project_references': project_references,
            'external_calls': external_calls,
            'events_published': events_published,
            'events_subscribed': events_subscribed
        }

    def _extract_architecture_patterns(self, service: Service) -> List[str]:
        """Extract architecture patterns from service description."""
        patterns = []
        description = service.description or ""
        
        if "CQRS" in description or "MediatR" in description:
            patterns.append("CQRS (Command Query Responsibility Segregation)")
        if "DI Container" in description:
            patterns.append("Dependency Injection")
        if "Message Bus" in description or "MassTransit" in description:
            patterns.append("Event-Driven Architecture")
        
        # Use regex to avoid CodeQL false positive (lists ASP.NET as a potential URL domain)
        # Matches "ASP.NET" or "Web SDK" as whole words/phrases
        if "Web SDK" in description or re.search(r'\bASP\.NET\b', description, re.IGNORECASE):
            patterns.append("ASP.NET Core Web API")
        
        return patterns

    async def _generate_responsibility(self, service: Service, controllers: List[Symbol]) -> str:
        """Use LLM to generate a high-level responsibility description."""
        controller_names = [c.name for c in controllers[:MAX_CONTROLLERS_FOR_LLM]]
        
        # Query enriched symbols with smart prioritization based on service type
        enriched_context_lines = []
        try:
            # Prioritize different symbol types based on service type
            priority_kinds = []
            if service.service_type.lower() in ['worker', 'service']:
                # For background services, prioritize workers and consumers
                query = select(Symbol).filter(
                    Symbol.service_id == service.id,
                    Symbol.ai_enrichment.is_not(None)
                ).order_by(
                    # Prioritize BackgroundService, Consumer, Worker classes
                    (Symbol.name.like('%BackgroundService%') | 
                     Symbol.name.like('%Consumer%') | 
                     Symbol.name.like('%Worker%')).desc(),
                    Symbol.id
                ).limit(15)
            else:
                # For APIs, prioritize controllers and services
                query = select(Symbol).filter(
                    Symbol.service_id == service.id,
                    Symbol.ai_enrichment.is_not(None)
                ).order_by(
                    (Symbol.name.like('%Controller%') | 
                     Symbol.name.like('%Service%')).desc(),
                    Symbol.id
                ).limit(15)
            
            result = await self.session.execute(query)
            enriched_symbols = result.scalars().all()
            
            for sym in enriched_symbols:
                enrichment = sym.ai_enrichment
                if isinstance(enrichment, dict):
                    business_purpose = enrichment.get('business_purpose', '')
                    functional_summary = enrichment.get('functional_summary', '')
                    # Skip generic fallbacks
                    if business_purpose and 'AI Analysis (Unstructured)' not in business_purpose:
                        # Include both business_purpose and functional_summary for richer context
                        context_line = f"  - {sym.name}: {business_purpose}"
                        if functional_summary and len(functional_summary) > 20:
                            context_line += f" ({functional_summary[:100]}...)" if len(functional_summary) > 100 else f" ({functional_summary})"
                        enriched_context_lines.append(context_line)
        except Exception as e:
            logger.debug(f"Could not fetch enrichment context: {e}")
        
        enriched_context = "\n".join(enriched_context_lines) if enriched_context_lines else "No enriched context available"
        
        # Gather additional context: Dependencies
        dependency_context = await self._get_dependency_context(service)
        
        # Gather additional context: Events & Messaging
        event_context = await self._get_event_context(service)
        
        # Construct a prompt for the LLM with enriched context
        prompt = f"""You are analyzing a {service.service_type} service to understand its business responsibility.

Service Name: {service.name}
Type: {service.service_type}
Controllers: {', '.join(controller_names) if controller_names else 'None detected'}
Namespace: {service.root_namespace or 'Unknown'}

Business Context from Code Analysis:
{enriched_context}

{dependency_context}

{event_context}

IMPORTANT: Focus on WHAT this service accomplishes for the business, NOT HOW it implements it.
- Emphasize business value, domain purpose, and outcomes
- Avoid technical implementation details (e.g., "uses background workers", "containerized", "batch processing")
- Instead, describe the business problem it solves and the value it provides
- Use domain language relevant to the business context (e.g., healthcare, orders, patients, workflows)

Provide a 2-3 sentence description of this service's business responsibility."""
        
        try:
            client = self.llm._get_client()
            if not client:
                raise ValueError("LLM client not available")
            
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=self.llm.model,
                messages=[
                    {"role": "system", "content": "You are an expert software architect analyzing microservices."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=400  # Increased from 200 for better responses
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"LLM generation failed: {e}")
            # Fallback - now uses enriched context if available
            if enriched_context_lines:
                # Extract first business purpose for fallback
                return f"The {service.name} is responsible for {enriched_context_lines[0].split(': ', 1)[1] if ': ' in enriched_context_lines[0] else 'core business logic'} and related operations within the system."
            elif controllers:
                domains = [c.name.replace('Controller', '').replace('Api', '') for c in controllers[:3]]
                return f"The {service.name} is responsible for managing {', '.join(domains)} and related operations within the system."
            return f"The {service.name} is a {service.service_type} service in the system architecture."
    
    async def _get_dependency_context(self, service: Service) -> str:
        """Extract dependency context to understand what external systems this service interacts with."""
        try:
            from sqlalchemy import select
            
            # Get dependencies for this repository
            result = await self.session.execute(
                select(Dependency).filter(
                    Dependency.repository_id == service.repository_id
                ).limit(10)
            )
            dependencies = result.scalars().all()
            
            if not dependencies:
                return ""
            
            # Extract key external dependencies (databases, message brokers, caches)
            key_deps = []
            for dep in dependencies:
                name = dep.package_name.lower()
                if 'rabbitmq' in name or 'masstransit' in name:
                    key_deps.append("Message Queue (RabbitMQ)")
                elif 'entityframework' in name or 'sqlserver' in name or 'postgres' in name:
                    key_deps.append("Relational Database")
                elif 'redis' in name or 'stackexchange' in name:
                    key_deps.append("Cache (Redis)")
                elif 'mongodb' in name:
                    key_deps.append("Document Database (MongoDB)")
            
            if key_deps:
                unique_deps = list(set(key_deps))
                return f"External Systems: {', '.join(unique_deps)}"
            return ""
        except Exception as e:
            logger.debug(f"Could not fetch dependency context: {e}")
            return ""
    
    async def _get_event_context(self, service: Service) -> str:
        """Extract event/messaging context to understand what events this service publishes or subscribes to."""
        try:
            # Get published events
            pub_result = await self.session.execute(
                select(PublishedEvent).filter(
                    PublishedEvent.service_id == service.id
                ).limit(5)
            )
            published = pub_result.scalars().all()
            
            # Get subscribed events
            sub_result = await self.session.execute(
                select(EventSubscription).filter(
                    EventSubscription.service_id == service.id
                ).limit(5)
            )
            subscribed = sub_result.scalars().all()
            
            context_parts = []
            if published:
                event_names = [e.event_name for e in published[:3]]
                context_parts.append(f"Publishes: {', '.join(event_names)}")
            if subscribed:
                event_names = [e.event_name for e in subscribed[:3]]
                context_parts.append(f"Subscribes: {', '.join(event_names)}")
            
            if context_parts:
                return "Event/Messaging Context:\n" + "\n".join(f"  - {part}" for part in context_parts)
            return ""
        except Exception as e:
            logger.debug(f"Could not fetch event context: {e}")
            return ""

    def _generate_overview(self, service: Service) -> str:
        """Generate overview section."""
        return f"""- **Type**: {service.service_type}
- **Framework**: {service.framework_version or 'Not specified'}
- **Root Namespace**: `{service.root_namespace or 'Not specified'}`
- **Project Path**: `{service.project_path}`"""

    def _generate_architecture_section(self, patterns: List[str]) -> str:
        """Generate architecture patterns section."""
        if not patterns:
            return "_No specific architecture patterns detected._"
        
        lines = ["**Detected Patterns:**"]
        for pattern in patterns:
            lines.append(f"- {pattern}")
        return "\n".join(lines)

    def _generate_api_section(self, controllers: List[Symbol], methods: Dict[str, List[Symbol]]) -> str:
        """Generate markdown list of API endpoints."""
        if not controllers:
            return "_No API endpoints detected._"
            
        lines = []
        for controller in controllers:
            lines.append(f"\n### {controller.name}")
            
            # Get methods for this controller
            controller_fqn = controller.fully_qualified_name
            controller_methods = methods.get(controller_fqn, [])
            
            if controller_methods:
                lines.append(f"\n**Endpoints ({len(controller_methods)}):**")
                for method in controller_methods[:MAX_METHODS_PER_CONTROLLER]:
                    # Extract HTTP verb using helper
                    http_verb = self._extract_http_verb(method.name)
                    lines.append(f"- `{http_verb}` **{method.name}**")
                    
                if len(controller_methods) > MAX_METHODS_PER_CONTROLLER:
                    remaining = len(controller_methods) - MAX_METHODS_PER_CONTROLLER
                    lines.append(f"- *...and {remaining} more endpoints*")
            else:
                # Fallback to child_count if available
                child_count = getattr(controller, 'child_count', 'Unknown')
                lines.append(f"\n*Methods: {child_count}*")
            
        return "\n".join(lines)

    def _extract_http_verb(self, method_name: str) -> str:
        """Extract HTTP verb from method name."""
        if method_name.startswith("Get"):
            return "GET"
        elif method_name.startswith("Post"):
            return "POST"
        elif method_name.startswith("Put"):
            return "PUT"
        elif method_name.startswith("Delete"):
            return "DELETE"
        elif method_name.startswith("Patch"):
            return "PATCH"
        return "HTTP"

    def _generate_dependency_section(
        self, 
        dependencies: List[Dependency], 
        project_refs: List[ProjectReference],
        external_calls: List[OutgoingApiCall]
    ) -> str:
        """Generate dependencies section."""
        lines = []
        
        # NuGet/NPM Packages
        dep_type = "NuGet Packages" if dependencies and dependencies[0].dependency_type == "nuget" else "Package Dependencies"
        lines.append(f"### {dep_type}")
        
        if dependencies:
            for dep in dependencies[:MAX_DEPENDENCIES_DISPLAY]:
                version = f" ({dep.package_version})" if dep.package_version else ""
                lines.append(f"- **{dep.package_name}**{version}")
            
            if len(dependencies) > MAX_DEPENDENCIES_DISPLAY:
                remaining = len(dependencies) - MAX_DEPENDENCIES_DISPLAY
                lines.append(f"- *...and {remaining} more packages*")
        else:
            lines.append("_No package dependencies found._")
        
        # Project References
        lines.append("\n### Project References")
        if project_refs:
            for ref in project_refs[:MAX_PROJECT_REFS_DISPLAY]:
                target = Path(ref.target_project_path).stem
                lines.append(f"- {target}")
            if len(project_refs) > MAX_PROJECT_REFS_DISPLAY:
                remaining = len(project_refs) - MAX_PROJECT_REFS_DISPLAY
                lines.append(f"- *...and {remaining} more projects*")
        else:
            lines.append("_No project references found._")
        
        # External Services
        lines.append("\n### External Services")
        if external_calls:
            # Group by URL to avoid duplicates
            unique_calls = {}
            for call in external_calls:
                key = f"{call.http_method} {call.url}"
                if key not in unique_calls:
                    unique_calls[key] = call
            
            for call in list(unique_calls.values())[:MAX_EXTERNAL_CALLS_DISPLAY]:
                lines.append(f"- `{call.http_method}` {call.url}")
            
            if len(unique_calls) > MAX_EXTERNAL_CALLS_DISPLAY:
                remaining = len(unique_calls) - MAX_EXTERNAL_CALLS_DISPLAY
                lines.append(f"- *...and {remaining} more external calls*")
        else:
            lines.append("_No external service calls detected._")
            
        return "\n".join(lines)

    def _generate_event_section(self, published: List[PublishedEvent], subscribed: List[EventSubscription]) -> str:
        """Generate events & messaging section."""
        lines = []
        
        lines.append("### Publishes")
        if published:
            for event in published[:MAX_EVENTS_DISPLAY]:
                broker = event.messaging_library or 'Unknown broker'
                lines.append(f"- **{event.event_type_name}** - {broker}")
            if len(published) > MAX_EVENTS_DISPLAY:
                remaining = len(published) - MAX_EVENTS_DISPLAY
                lines.append(f"- *...and {remaining} more events*")
        else:
            lines.append("_No events published._")
            
        lines.append("\n### Subscribes")
        if subscribed:
            for sub in subscribed[:MAX_EVENTS_DISPLAY]:
                broker = sub.messaging_library or 'Unknown broker'
                lines.append(f"- **{sub.event_type_name}** - {broker}")
            if len(subscribed) > MAX_EVENTS_DISPLAY:
                remaining = len(subscribed) - MAX_EVENTS_DISPLAY
                lines.append(f"- *...and {remaining} more subscriptions*")
        else:
            lines.append("_No event subscriptions._")
            
        return "\n".join(lines)

    def _generate_technical_section(self, service: Service) -> str:
        """Generate technical details section with null safety."""
        entry_points_count = len(service.entry_points) if service.entry_points else 0
        description = service.description or "No detection information available"
        doc_path = service.documentation_path or "Not yet generated"
        
        return f"""**Service Metadata:**
- Entry Points: {entry_points_count} controllers
- Detection Reasons: {description}

**File Locations:**
- Project: `{service.project_path}`
- Documentation: `{doc_path}`
"""

    async def save_documentation(self, service: Service, content: str) -> str:
        """
        Save documentation to filesystem and return the relative path.
        Uses cross-platform path handling.
        """
        # Create docs directory structure
        base_dir = Path(get_settings().repo_cache_dir).parent
        docs_dir = base_dir / "docs" / "services"
        
        # Ensure directory exists
        await asyncio.to_thread(docs_dir.mkdir, parents=True, exist_ok=True)
        
        # Build guaranteed unique filename: repo_id + repo_name + service_path
        repo_id = service.repository_id
        repo_name = self._sanitize_filename(service.repository.name if service.repository else "unknown")
        service_path = self._sanitize_filename(service.name)
        
        # Combined filename
        unique_filename = f"{repo_id}_{repo_name}_{service_path}.md"
        doc_file = docs_dir / unique_filename
        
        # Write file
        await asyncio.to_thread(doc_file.write_text, content, encoding='utf-8')
        
        # Return relative path (cross-platform)
        relative_path = os.path.relpath(doc_file, base_dir)
        logger.info(f"Saved documentation to: {relative_path}")
        
        return relative_path

    def _sanitize_filename(self, name: str) -> str:
        """
        Sanitize service name for safe filename.
        Removes/replaces characters that could cause issues.
        """
        # Replace dots, spaces, and path separators with underscores
        safe = name.replace(".", "_").replace(" ", "_").replace("/", "_").replace("\\", "_")
        # Remove any other potentially problematic characters
        safe = re.sub(r'[<>:"|?*]', '', safe)
        # Limit length (reduced since we combine multiple parts)
        return safe[:100]
