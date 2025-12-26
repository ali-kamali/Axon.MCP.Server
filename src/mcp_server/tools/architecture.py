import re
from typing import List, Optional, Dict, Set
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcp.types import TextContent

from src.database.models import Symbol, File, Repository, Relation, OutgoingApiCall, ApiEndpointLink, PublishedEvent, EventLink, EventSubscription, Service
from src.database.session import get_async_session
from src.config.enums import SymbolKindEnum, RelationTypeEnum
from src.utils.logging_config import get_logger
from src.utils.layer_detector import LayerDetector
from src.extractors.pattern_detector import PatternDetector
from src.extractors.api_extractor import ApiEndpointExtractor
from src.mcp_server.formatters.hierarchy import format_call_chain

logger = get_logger(__name__)


async def analyze_architecture(
    repository_id: int,
) -> List[TextContent]:
    """
    Analyze repository architecture and detect patterns.
    
    Returns comprehensive architecture analysis including:
    - Project hierarchy (services and class libraries)
    - Design patterns detected
    - Architectural layers
    - Anti-patterns

    Args:
        repository_id: Repository ID

    Returns:
        Architecture analysis with project structure and detected patterns
    """
    try:
        async with get_async_session() as session:
            
            # Get repository info
            result = await session.execute(
                select(Repository).where(Repository.id == repository_id)
            )
            repo = result.scalar_one_or_none()
            
            if not repo:
                return [TextContent(type="text", text=f"Repository ID {repository_id} not found")]
            
            formatted = [f"# Architecture Analysis: {repo.name}\n\n"]
            
            # ============================================================
            # SECTION 1: PROJECT HIERARCHY
            # ============================================================
            
            # Get all services for hierarchy
            services_result = await session.execute(
                select(Service)
                .where(Service.repository_id == repository_id)
                .order_by(Service.service_type, Service.name)
            )
            services = services_result.scalars().all()
            
            if services:
                # Separate by type
                apis = [s for s in services if s.service_type == "API"]
                workers = [s for s in services if s.service_type == "Worker"]
                consoles = [s for s in services if s.service_type == "Console"]
                libraries = [s for s in services if s.service_type == "Library"]
                
                formatted.append("## Project Structure\n\n")
                
                # Show deployable services with their related libraries
                deployable = []
                if apis:
                    deployable.extend(apis)
                if workers:
                    deployable.extend(workers)
                if consoles:
                    deployable.extend(consoles)
                
                if deployable:
                    formatted.append("### Deployable Services\n\n")
                    for service in deployable:
                        formatted.append(f"**{service.name}** ({service.service_type})\n")
                        if service.framework_version:
                            formatted.append(f"- Framework: {service.framework_version}\n")
                        if service.root_namespace:
                            formatted.append(f"- Namespace: `{service.root_namespace}`\n")
                        if service.entry_points:
                            formatted.append(f"- Entry Points: {len(service.entry_points)}\n")
                        
                        # Find related libraries (same namespace prefix)
                        if service.name:
                            parts = service.name.rsplit('.', 1)
                            if len(parts) == 2:
                                prefix = parts[0]
                                related = [lib for lib in libraries if lib.name and lib.name.startswith(prefix + ".")]
                                
                                if related:
                                    formatted.append(f"- Related Libraries:\n")
                                    for lib in related:
                                        # Determine layer (defensive null check)
                                        lib_name_lower = (lib.name or "").lower()
                                        layer = "Library"
                                        if "domain" in lib_name_lower:
                                            layer = "Domain"
                                        elif "application" in lib_name_lower:
                                            layer = "Application"
                                        elif "infrastructure" in lib_name_lower:
                                            layer = "Infrastructure"
                                        elif "shared" in lib_name_lower or "common" in lib_name_lower:
                                            layer = "Shared"
                                        formatted.append(f"  - {lib.name} ({layer})\n")
                        
                        formatted.append("\n")
                
                # Show standalone libraries
                if libraries:
                    shown_library_names = set()
                    for service in deployable:
                        if service.name:
                            parts = service.name.rsplit('.', 1)
                            if len(parts) == 2:
                                prefix = parts[0]
                                for lib in libraries:
                                    if lib.name and lib.name.startswith(prefix + "."):
                                        shown_library_names.add(lib.name)
                    
                    standalone = [lib for lib in libraries if lib.name not in shown_library_names]
                    
                    if standalone:
                        formatted.append("### Standalone Libraries\n\n")
                        for lib in standalone:
                            # Defensive null check
                            lib_name_lower = (lib.name or "").lower()
                            layer = "Unknown"
                            if "domain" in lib_name_lower:
                                layer = "Domain"
                            elif "application" in lib_name_lower:
                                layer = "Application"
                            elif "infrastructure" in lib_name_lower:
                                layer = "Infrastructure"
                            formatted.append(f"- {lib.name} ({layer})\n")
                        formatted.append("\n")
            else:
                formatted.append("## Project Structure\n\n")
                formatted.append("No services detected in this repository.\n\n")
            
            # ============================================================
            # SECTION 2: PATTERN DETECTION
            # ============================================================
            # Detect patterns
            detector = PatternDetector(session)
            patterns = await detector.detect_patterns(repository_id)
            
            if patterns:
                formatted.append(f"## Detected Patterns\n\n")
                formatted.append(f"Total: {len(patterns)} patterns detected\n\n")
                
                # Group patterns by type
                by_type = {}
                for pattern in patterns:
                    pattern_type = pattern.pattern_type
                    if pattern_type not in by_type:
                        by_type[pattern_type] = []
                    by_type[pattern_type].append(pattern)
                
                # Design Patterns
                if 'design_pattern' in by_type:
                    formatted.append(f"### Design Patterns ({len(by_type['design_pattern'])})\n\n")
                    for pattern in by_type['design_pattern']:
                        formatted.append(
                            f"**{pattern.pattern_name}**\n"
                            f"- Confidence: {pattern.confidence:.0%}\n"
                            f"- Description: {pattern.description}\n"
                            f"- Evidence:\n"
                        )
                        for evidence in pattern.evidence:
                            formatted.append(f"  - {evidence}\n")
                        formatted.append("\n")
                
                # Architectural Layers
                if 'architectural_layer' in by_type:
                    formatted.append(f"### Architectural Layers ({len(by_type['architectural_layer'])})\n\n")
                    for pattern in by_type['architectural_layer']:
                        formatted.append(
                            f"**{pattern.pattern_name}**\n"
                            f"{pattern.description}\n\n"
                        )
                
                # Anti-Patterns
                if 'anti_pattern' in by_type:
                    formatted.append(f"### ⚠️ Anti-Patterns ({len(by_type['anti_pattern'])})\n\n")
                    for pattern in by_type['anti_pattern']:
                        formatted.append(
                            f"**{pattern.pattern_name}**\n"
                            f"- Confidence: {pattern.confidence:.0%}\n"
                            f"- Description: {pattern.description}\n"
                            f"- Recommendations:\n"
                        )
                        for evidence in pattern.evidence:
                            formatted.append(f"  - {evidence}\n")
                        formatted.append("\n")
            else:
                formatted.append(f"## Detected Patterns\n\n")
                formatted.append(f"No patterns detected in repository.\n\n")
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_analyze_architecture_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to analyze architecture: {str(e)}",
            )
        ]


async def trace_request_flow(
    endpoint: str,
    repository_id: int,
    depth: int = 5,
) -> List[TextContent]:
    """
    Trace request flow through application layers, including cross-service calls.

    Args:
        endpoint: API endpoint (e.g., 'POST /api/users')
        repository_id: Repository ID
        depth: Maximum depth to trace (default: 5, max: 10)

    Returns:
        Request flow trace with layer information and statistics
    """
    try:
        async with get_async_session() as session:
            # Parse endpoint
            parts = endpoint.split(' ', 1)
            if len(parts) == 2:
                http_method, route = parts
                http_method = http_method.upper()
            else:
                route = endpoint
                http_method = None
            
            # API endpoints are stored as Symbol entries with kind='ENDPOINT'
            # The details are in structured_docs: {http_method, route, controller, action, ...}
            query = (
                select(Symbol, File)
                .join(File, Symbol.file_id == File.id)
                .where(
                    File.repository_id == repository_id,
                    Symbol.kind == SymbolKindEnum.ENDPOINT
                )
            )
            
            result = await session.execute(query)
            endpoint_symbols = result.all()
            
            matching_endpoint = None
            matching_symbol = None
            matching_file = None
            
            # Strategy 1: Direct match (Backend URL)
            for symbol, file in endpoint_symbols:
                docs = symbol.structured_docs or {}
                ep_http_method = docs.get('http_method', '')
                ep_route = docs.get('route', '')
                
                # Skip if http_method filter doesn't match
                if http_method and ep_http_method != http_method:
                    continue
                
                # Simple path matching logic
                # Convert route pattern to regex: /users/{id} -> /users/[^/]+
                if ep_route:
                    pattern = re.sub(r'\{[^}]+\}', '[^/]+', ep_route)
                    if re.match(f"^{pattern}$", route, re.IGNORECASE):
                        matching_endpoint = docs
                        matching_symbol = symbol
                        matching_file = file
                        break
            
            # Strategy 2: Fallback - Try to find by partial match
            if not matching_endpoint:
                for symbol, file in endpoint_symbols:
                    docs = symbol.structured_docs or {}
                    ep_http_method = docs.get('http_method', '')
                    ep_route = docs.get('route', '')
                    
                    # Skip if http_method filter doesn't match
                    if http_method and ep_http_method != http_method:
                        continue
                    
                    if ep_route and (ep_route in route or route in ep_route):
                        matching_endpoint = docs
                        matching_symbol = symbol
                        matching_file = file
                        break

            if not matching_endpoint:
                return [TextContent(type="text", text=f"Endpoint not found in repository {repository_id}: {endpoint}\n\n"
                    f"💡 Use `find_api_endpoints(repository_id={repository_id})` to see available endpoints.")]
            
            # Get the controller method symbol that implements this endpoint
            # The endpoint symbol itself points to the controller method via line_number
            # Try 1: Exact line match
            controller_method_result = await session.execute(
                select(Symbol)
                .where(
                    Symbol.file_id == matching_symbol.file_id,
                    Symbol.kind == SymbolKindEnum.METHOD,
                    Symbol.start_line == matching_symbol.start_line
                )
            )
            method_symbol = controller_method_result.scalars().first()
            
            # Try 2: Fallback - Match by name and controller
            if not method_symbol:
                ep_controller = matching_endpoint.get('controller')
                ep_action = matching_endpoint.get('action')
                
                if ep_controller and ep_action:
                    # Try to find method with action name in the same file
                    # This handles cases where line numbers might be slightly off
                    method_result = await session.execute(
                        select(Symbol)
                        .where(
                            Symbol.file_id == matching_symbol.file_id,
                            Symbol.kind == SymbolKindEnum.METHOD,
                            Symbol.name == ep_action
                        )
                    )
                    method_symbol = method_result.scalars().first()
            
            # If still not found, use the endpoint symbol itself (will likely have no calls)
            if not method_symbol:
                logger.warning(f"Could not find method symbol for endpoint {endpoint}, using endpoint symbol")
                method_symbol = matching_symbol
            
            # REFACTORED: Use CallGraphTraverser instead of custom _build_call_chain
            from src.utils.call_graph_traversal import CallGraphTraverser, TraversalConfig, TraversalDirection
            
            traverser = CallGraphTraverser(session)
            config = TraversalConfig(
                depth=min(depth, 10),  # Cap at 10 for safety
                direction=TraversalDirection.DOWNSTREAM,
                relation_types=[
                    RelationTypeEnum.CALLS,
                    RelationTypeEnum.IMPLEMENTS,
                    RelationTypeEnum.INHERITS,
                    RelationTypeEnum.USES,
                ],
                max_symbols=100,  # Increased limit for request traces
                max_tokens=20000,  # Increased token budget
                include_source_code=False,  # Only signatures for performance
                include_signatures=True,
                resolve_interfaces=True,  # Enable .NET DI tracing
                detect_cqrs_handlers=True,  # Enable CQRS detection
            )
            
            result = await traverser.traverse(symbol_id=method_symbol.id, config=config)
            
            if not result:
                return [TextContent(type="text", text=f"Failed to trace flow from controller method")]
            
            # Extract statistics from traversal result
            stats = {
                "total_symbols": result.total_symbols,
                "max_depth_reached": result.max_depth_reached,
                "interface_resolutions": result.interface_resolutions,
                "cqrs_handlers_found": result.cqrs_handlers_found,
                "cycles_detected": result.cycles_detected,
            }
            
            # Count layers visited
            layers_visited = set()
            for symbol_node in [result.root_symbol] + result.related_symbols:
                if symbol_node.layer:
                    layers_visited.add(symbol_node.layer)
            
            stats["layers_visited"] = layers_visited
            stats["cross_service_calls"] = 0  # TODO: Extract from relation types
            stats["event_publications"] = 0   # TODO: Extract from relation types
            
            # Format results
            ep_http_method = matching_endpoint.get('http_method', 'GET')
            ep_route = matching_endpoint.get('route', '/')
            ep_controller = matching_endpoint.get('controller', 'Unknown')
            ep_action = matching_endpoint.get('action', 'Unknown')
            
            formatted = [
                f"# Request Flow Trace: {endpoint}\n\n",
                f"**Endpoint**: `{ep_http_method} {ep_route}`\n",
                f"**Controller**: {ep_controller}.{ep_action}\n",
                f"**File**: {matching_file.path}:{matching_symbol.start_line}\n\n",
                "## Statistics:\n\n",
                f"- **Total Symbols**: {stats['total_symbols']}\n",
                f"- **Max Depth Reached**: {stats['max_depth_reached']}/{min(depth, 10)}\n",
                f"- **Layers Visited**: {', '.join(sorted(stats['layers_visited'])) if stats['layers_visited'] else 'None'}\n",
                f"- **Interface Resolutions**: {stats['interface_resolutions']} (DI tracing)\n",
                f"- **CQRS Handlers**: {stats['cqrs_handlers_found']}\n",
            ]
            
            if stats['cycles_detected'] > 0:
                formatted.append(f"- **Cycles Detected**: {stats['cycles_detected']}\n")
            
            formatted.append("\n## Flow:\n\n")
            
            # Use the traverser's markdown formatter
            flow_markdown = traverser.format_result_markdown(result, include_stats=False)
            formatted.append(flow_markdown)
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_trace_request_flow_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to trace request flow: {str(e)}",
            )
        ]





async def find_api_endpoints(
    repository_id: int,
    http_method: Optional[str] = None,
    route_pattern: Optional[str] = None,
) -> List[TextContent]:
    """
    Find all API endpoints in repository.

    Args:
        repository_id: Repository ID
        http_method: Optional HTTP method filter
        route_pattern: Optional route pattern filter

    Returns:
        List of API endpoints
    """
    try:
        async with get_async_session() as session:
            
            # Extract endpoints
            extractor = ApiEndpointExtractor(session)
            endpoints = await extractor.extract_endpoints(repository_id)
            
            # Apply filters
            if http_method:
                endpoints = [e for e in endpoints if e.http_method.upper() == http_method.upper()]
            
            if route_pattern:
                # Convert wildcard pattern to regex
                pattern = route_pattern.replace('*', '.*')
                pattern = f"^{pattern}$"
                endpoints = [e for e in endpoints if re.match(pattern, e.route)]
            
            if not endpoints:
                return [TextContent(type="text", text=f"No API endpoints found in repository")]
            
            # Group by HTTP method
            by_method = {}
            for endpoint in endpoints:
                method = endpoint.http_method
                if method not in by_method:
                    by_method[method] = []
                by_method[method].append(endpoint)
            
            # Format results
            formatted = [
                f"# API Endpoints\n",
                f"Total: {len(endpoints)} endpoints\n\n"
            ]
            
            for method, endpoints_list in sorted(by_method.items()):
                formatted.append(f"## {method} ({len(endpoints_list)})\n\n")
                
                for endpoint in sorted(endpoints_list, key=lambda e: e.route):
                    formatted.append(f"### `{method} {endpoint.route}`\n")
                    formatted.append(f"- **Controller**: {endpoint.controller}\n")
                    formatted.append(f"- **Action**: {endpoint.action}\n")
                    formatted.append(f"- **File**: {endpoint.file_path}:{endpoint.line_number}\n")
                    
                    if endpoint.requires_auth:
                        formatted.append(f"- **Auth**: 🔒 Required\n")
                    
                    if endpoint.parameters:
                        formatted.append(f"- **Parameters**:\n")
                        for param in endpoint.parameters:
                            param_name = param.get('name', 'unknown')
                            param_type = param.get('type', 'unknown')
                            formatted.append(f"  - `{param_name}`: {param_type}\n")
                    
                    formatted.append("\n")
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_find_api_endpoints_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to find API endpoints: {str(e)}",
            )
        ]
