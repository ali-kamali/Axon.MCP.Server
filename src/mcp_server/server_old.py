"""MCP server for ChatGPT integration."""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Set

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool, Resource
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.services.search_service import SearchService
from src.config.enums import (
    LanguageEnum,
    MCPToolEnum,
    RelationTypeEnum,
    SourceControlProviderEnum,
    SymbolKindEnum,
)
from src.database.models import (
    ConfigurationEntry,
    Dependency,
    Document,
    File,
    Relation,
    Repository,
    Symbol,
    Chunk,
    ApiEndpointLink,
    EventLink,
    GatewayRoute,
)
from src.database.session import get_async_session
from src.utils.logging_config import get_logger
from src.utils.metrics import mcp_tool_calls_total, mcp_tool_duration
from src.utils.call_graph_traversal import CallGraphTraverser, TraversalConfig, TraversalDirection
from src.utils.text_to_sql import TextToSQLTranslator
from src.services.link_service import get_connected_endpoints_for_symbol

logger = get_logger(__name__)

# Create module-level server instance
mcp = Server("axon-mcp-server")


class AxonMCPServer:
    """MCP server for ChatGPT integration."""

    def __init__(self):
        """Initialize MCP server."""
        self.server = mcp
        self._register_tools()
        logger.info("mcp_server_initialized")

    def _register_tools(self):
        """Register all MCP tools."""
        # Tools are registered at module level using decorators
        # This method is kept for initialization tracking
        pass

    def _format_search_results(self, results: List[Dict], query: str) -> str:
        """Format search results for ChatGPT display."""
        if not results:
            return f"No results found for query: '{query}'"

        formatted = [f"Found {len(results)} results for '{query}':\n"]

        for i, result in enumerate(results, 1):
            # Include code snippet if available
            code_preview = ""
            if result.get('code_snippet'):
                snippet = result['code_snippet'][:200]  # First 200 chars
                if len(result['code_snippet']) > 200:
                    snippet += "..."
                code_preview = f"\n   Code Preview:\n   ```\n   {snippet}\n   ```\n"
            
            formatted.append(
                f"\n{i}. **{result['name']}** ({result['kind']})\n"
                f"   📍 {result['repository']} / {result['file']} (lines {result['lines']})\n"
                f"   🔍 Relevance: {result['relevance_score']} ({result.get('match_type', 'unknown')})\n"
                f"   📝 Signature: `{result['signature']}`\n"
                f"   📄 {result['documentation']}\n"
                f"{code_preview}"
                f"   🔗 IDs: symbol_id={result['symbol_id']}, file_id={result['file_id']}, repo_id={result['repository_id']}\n"
                f"   💡 Use get_symbol_context(symbol_id={result['symbol_id']}) for full details\n"
            )

        return "".join(formatted)

    def _format_symbol_context(self, context: Dict) -> str:
        """Format symbol context for ChatGPT display."""
        symbol = context["symbol"]
        location = context["location"]

        formatted = [
            f"## {symbol['name']} ({symbol['kind']})\n\n",
            f"**Location**: {location['repository']}/{location['file']} (lines {location['lines']})\n\n",
            f"**IDs**: symbol_id={symbol['id']}, file_id={symbol['file_id']}, repository_id={symbol['repository_id']}\n\n",
            f"**Signature**: `{symbol['signature']}`\n\n",
        ]

        if symbol["documentation"]:
            formatted.append(f"**Documentation**: {symbol['documentation']}\n\n")

        if symbol["parameters"]:
            formatted.append("**Parameters**:\n")
            for param in symbol["parameters"]:
                param_type = (
                    param.get("type", "unknown")
                    if isinstance(param, dict)
                    else "unknown"
                )
                param_name = (
                    param.get("name", str(param))
                    if isinstance(param, dict)
                    else str(param)
                )
                formatted.append(f"- `{param_name}`: {param_type}\n")
            formatted.append("\n")

        if symbol["return_type"]:
            formatted.append(f"**Returns**: {symbol['return_type']}\n\n")

        if symbol["complexity"]:
            formatted.append(f"**Complexity**: {symbol['complexity']}\n\n")

        # Add relationships if present
        if "relationships" in context:
            rels = context["relationships"]
            if any(rels.values()):
                formatted.append("**Relationships**:\n\n")

                if rels["calls"]:
                    formatted.append("*Calls*:\n")
                    for rel in rels["calls"]:
                        formatted.append(
                            f"- {rel['name']} (ID: {rel['id']}, {rel['kind']})\n"
                        )
                    formatted.append("\n")

                if rels["called_by"]:
                    formatted.append("*Called by*:\n")
                    for rel in rels["called_by"]:
                        formatted.append(
                            f"- {rel['name']} (ID: {rel['id']}, {rel['kind']})\n"
                        )
                    formatted.append("\n")

                if rels["inherits_from"]:
                    formatted.append("*Inherits from*:\n")
                    for rel in rels["inherits_from"]:
                        formatted.append(
                            f"- {rel['name']} (ID: {rel['id']}, {rel['kind']})\n"
                        )
                    formatted.append("\n")

                if rels["inherited_by"]:
                    formatted.append("*Inherited by*:\n")
                    for rel in rels["inherited_by"]:
                        formatted.append(
                            f"- {rel['name']} (ID: {rel['id']}, {rel['kind']})\n"
                        )
                    formatted.append("\n")

        # Add source code if available
        if "source_code" in context:
            formatted.append("**Source Code**:\n")
            formatted.append(f"```{location['language']}\n")
            formatted.append(context["source_code"])
            formatted.append("\n```\n\n")

        # Add connected endpoints (Phase 3: The Linker)
        if "connected_endpoints" in context:
            conn = context["connected_endpoints"]
            if any(conn.values()):
                formatted.append("**Connected Endpoints (Cross-Service)**:\n\n")
                
                # Outgoing API calls
                if conn.get("outgoing_api_calls"):
                    formatted.append("*Outgoing API Calls*:\n")
                    for call in conn["outgoing_api_calls"]:
                        formatted.append(
                            f"- `{call['http_method']} {call['url_pattern']}`"
                        )
                        if call.get("linked_endpoint"):
                            ep = call["linked_endpoint"]
                            formatted.append(
                                f" → **{ep['name']}** in `{ep['repository']}`"
                                f" (confidence: {ep['match_confidence']}%)"
                            )
                        formatted.append("\n")
                    formatted.append("\n")
                
                # Incoming API calls
                if conn.get("incoming_api_calls"):
                    formatted.append("*Called By (Cross-Service)*:\n")
                    for call in conn["incoming_api_calls"]:
                        formatted.append(
                            f"- `{call['http_method']} {call['url_pattern']}` "
                            f"from `{call['source_repository']}` "
                            f"(confidence: {call['match_confidence']}%)\n"
                        )
                    formatted.append("\n")
                
                # Published events
                if conn.get("published_events"):
                    formatted.append("*Publishes Events*:\n")
                    for event in conn["published_events"]:
                        formatted.append(f"- **{event['event_type']}**")
                        if event.get("topic"):
                            formatted.append(f" to `{event['topic']}`")
                        if event.get("subscribers"):
                            subs = event["subscribers"]
                            formatted.append(f" ({len(subs)} subscriber(s))")
                        formatted.append("\n")
                    formatted.append("\n")
                
                # Subscribed events
                if conn.get("subscribed_events"):
                    formatted.append("*Subscribes To Events*:\n")
                    for sub in conn["subscribed_events"]:
                        formatted.append(f"- **{sub['event_type']}**")
                        if sub.get("queue"):
                            formatted.append(f" via `{sub['queue']}`")
                        if sub.get("publishers"):
                            pubs = sub["publishers"]
                            formatted.append(f" ({len(pubs)} publisher(s))")
                        formatted.append("\n")
                    formatted.append("\n")

        return "".join(formatted)

    def _format_repository_list(self, repos: List[Dict]) -> str:
        """Format repository list for ChatGPT display."""
        if not repos:
            return "No repositories available."

        formatted = [f"Available repositories ({len(repos)}):\n\n"]

        for repo in repos:
            # Format size
            size_mb = repo['size_bytes'] / (1024 * 1024) if repo['size_bytes'] > 0 else 0
            
            formatted.append(
                f"**{repo['name']}** ({repo['provider']})\n"
                f"  📦 Path: {repo['path_with_namespace']}\n"
                f"  🌿 Branch: {repo['default_branch']}\n"
                f"  📊 Status: {repo['status']}\n"
                f"  📄 Files: {repo['total_files']:,} | Symbols: {repo['total_symbols']:,} | Size: {size_mb:.1f} MB\n"
                f"  🔄 Last synced: {repo['last_synced'] or 'Never'}\n"
                f"  🔗 Repository ID: {repo['id']}\n"
                f"  🌐 URL: {repo['url']}\n"
                f"  💡 Use search_code(repository_name='{repo['name']}') to search this repo\n"
                f"  💡 Use get_file_content(repository_id={repo['id']}, file_path='...') to read files\n"
                f"\n"
            )

        return "".join(formatted)

    async def start(self):
        """Start MCP server with stdio transport."""
        logger.info("mcp_server_starting")
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


# Create a global instance for formatting methods with async lock for thread-safe initialization
_formatter_instance = None
_formatter_lock = asyncio.Lock()


async def _get_formatter():
    """Get or create formatter instance in a thread-safe manner."""
    global _formatter_instance
    if _formatter_instance is None:
        async with _formatter_lock:
            # Double-check pattern: another task might have created it while we waited
            if _formatter_instance is None:
                _formatter_instance = AxonMCPServer()
    return _formatter_instance


# Register tools at module level
@mcp.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool calls."""
    if name == MCPToolEnum.SEARCH_CODE.value:
        return await _search_code(
            query=arguments.get("query"),
            limit=arguments.get("limit", 10),
            repository_name=arguments.get("repository_name"),
            language=arguments.get("language"),
            symbol_kind=arguments.get("symbol_kind"),
        )
    elif name == MCPToolEnum.GET_SYMBOL_CONTEXT.value:
        return await _get_symbol_context(
            symbol_id=arguments.get("symbol_id"),
            include_relationships=arguments.get("include_relationships", True),
            depth=arguments.get("depth", 0),
            direction=arguments.get("direction", "downstream"),
            max_symbols=arguments.get("max_symbols", 50),
            relation_types=arguments.get("relation_types"),
        )
    elif name == MCPToolEnum.LIST_REPOSITORIES.value:
        return await _list_repositories(limit=arguments.get("limit", 20))
    elif name == MCPToolEnum.SEARCH_DOCUMENTATION.value:
        return await _search_documentation(
            query=arguments.get("query"),
            repository_id=arguments.get("repository_id"),
            doc_type=arguments.get("doc_type"),
            limit=arguments.get("limit", 10),
        )
    elif name == MCPToolEnum.SEARCH_CONFIGURATION.value:
        return await _search_configuration(
            key_pattern=arguments.get("key_pattern"),
            repository_id=arguments.get("repository_id"),
            environment=arguments.get("environment"),
            limit=arguments.get("limit", 20),
        )
    elif name == MCPToolEnum.LIST_DEPENDENCIES.value:
        return await _list_dependencies(
            repository_id=arguments.get("repository_id"),
            dependency_type=arguments.get("dependency_type"),
            limit=arguments.get("limit", 50),
        )
    elif name == MCPToolEnum.GET_FILE_CONTENT.value:
        return await _get_file_content(
            repository_id=arguments.get("repository_id"),
            file_path=arguments.get("file_path"),
            start_line=arguments.get("start_line"),
            end_line=arguments.get("end_line"),
        )
    elif name == MCPToolEnum.FIND_USAGES.value:
        return await _find_usages(
            symbol_id=arguments.get("symbol_id"),
            limit=arguments.get("limit", 50),
        )
    elif name == MCPToolEnum.FIND_IMPLEMENTATIONS.value:
        return await _find_implementations(
            interface_id=arguments.get("interface_id"),
        )
    elif name == MCPToolEnum.FIND_REFERENCES.value:
        return await _find_references(
            symbol_id=arguments.get("symbol_id"),
            reference_type=arguments.get("reference_type"),
            limit=arguments.get("limit", 50),
        )
    elif name == MCPToolEnum.GET_FILE_TREE.value:
        return await _get_file_tree(
            repository_id=arguments.get("repository_id"),
            path=arguments.get("path", ""),
            depth=arguments.get("depth", 3),
        )
    elif name == MCPToolEnum.LIST_SYMBOLS_IN_FILE.value:
        return await _list_symbols_in_file(
            repository_id=arguments.get("repository_id"),
            file_path=arguments.get("file_path"),
            symbol_kinds=arguments.get("symbol_kinds"),
        )
    elif name == MCPToolEnum.FIND_API_ENDPOINTS.value:
        return await _find_api_endpoints(
            repository_id=arguments.get("repository_id"),
            http_method=arguments.get("http_method"),
            route_pattern=arguments.get("route_pattern"),
        )
    elif name == MCPToolEnum.GET_CALL_HIERARCHY.value:
        return await _get_call_hierarchy(
            symbol_id=arguments.get("symbol_id"),
            direction=arguments.get("direction", "outbound"),
            depth=arguments.get("depth", 3),
        )
    elif name == MCPToolEnum.FIND_CALLERS.value:
        return await _find_callers(
            symbol_id=arguments.get("symbol_id"),
            limit=arguments.get("limit", 50),
        )
    elif name == MCPToolEnum.FIND_CALLEES.value:
        return await _find_callees(
            symbol_id=arguments.get("symbol_id"),
            limit=arguments.get("limit", 50),
        )
    elif name == MCPToolEnum.ANALYZE_ARCHITECTURE.value:
        return await _analyze_architecture(
            repository_id=arguments.get("repository_id"),
        )
    elif name == MCPToolEnum.SEARCH_BY_PATH.value:
        return await _search_by_path(
            repository_id=arguments.get("repository_id"),
            path_pattern=arguments.get("path_pattern"),
            limit=arguments.get("limit", 50),
        )
    elif name == MCPToolEnum.TRACE_REQUEST_FLOW.value:
        return await _trace_request_flow(
            endpoint=arguments.get("endpoint"),
            repository_id=arguments.get("repository_id"),
        )
    elif name == MCPToolEnum.GET_PROJECT_MAP.value:
        return await _get_project_map(
            repository_id=arguments.get("repository_id"),
            max_depth=arguments.get("max_depth", 2),
        )
    elif name == MCPToolEnum.GET_MODULE_SUMMARY.value:
        return await _get_module_summary(
            repository_id=arguments.get("repository_id"),
            module_path=arguments.get("module_path"),
            generate_if_missing=arguments.get("generate_if_missing", True),
        )
    elif name == MCPToolEnum.QUERY_CODEBASE_STRUCTURE.value:
        return await _query_codebase_structure(
            query=arguments.get("query"),
            repository_id=arguments.get("repository_id"),
            limit=arguments.get("limit", 50),
        )
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


@mcp.list_tools()
async def list_tools() -> List[Tool]:
    """List available tools."""
    return [
        Tool(
            name=MCPToolEnum.SEARCH_CODE.value,
            description="Search for code symbols across repositories",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (function name, class name, or description)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 10, max: 50)",
                        "default": 10,
                    },
                    "repository_name": {
                        "type": "string",
                        "description": "Filter by repository name",
                    },
                    "language": {
                        "type": "string",
                        "description": "Filter by programming language (csharp, javascript, typescript, vue, python)",
                    },
                    "symbol_kind": {
                        "type": "string",
                        "description": "Filter by symbol kind (function, class, method, etc.)",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name=MCPToolEnum.GET_SYMBOL_CONTEXT.value,
            description="Get detailed context for a specific symbol with recursive call graph traversal (Phase 3: Intelligent Traversal). Explore symbol relationships in depth, showing what a function calls or what calls it, with configurable depth.",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol_id": {
                        "type": "integer",
                        "description": "ID of the symbol to explore",
                    },
                    "include_relationships": {
                        "type": "boolean",
                        "description": "Include direct relationships (default: true)",
                        "default": True,
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Traversal depth: 0=just the symbol, 1=direct relations, 2+=recursive (default: 0, max: 5). Use 2-3 for understanding call chains.",
                        "default": 0,
                        "minimum": 0,
                        "maximum": 5,
                    },
                    "direction": {
                        "type": "string",
                        "description": "Traversal direction: 'downstream' (what this calls), 'upstream' (what calls this), 'both' (default: 'downstream')",
                        "enum": ["downstream", "upstream", "both"],
                        "default": "downstream",
                    },
                    "max_symbols": {
                        "type": "integer",
                        "description": "Maximum symbols to include in result to control size (default: 50)",
                        "default": 50,
                        "minimum": 1,
                        "maximum": 100,
                    },
                    "relation_types": {
                        "type": "array",
                        "description": "Relationship types to follow during traversal (default: ['CALLS', 'INHERITS', 'IMPLEMENTS', 'USES']). Options: 'CALLS', 'INHERITS', 'IMPLEMENTS', 'USES', 'IMPORTS', 'EXPORTS'",
                        "items": {
                            "type": "string",
                            "enum": ["CALLS", "INHERITS", "IMPLEMENTS", "USES", "IMPORTS", "EXPORTS"]
                        },
                        "default": ["CALLS", "INHERITS", "IMPLEMENTS", "USES"],
                    },
                },
                "required": ["symbol_id"],
            },
        ),
        Tool(
            name=MCPToolEnum.LIST_REPOSITORIES.value,
            description="List available repositories with their status and statistics",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of repositories to return (default: 20)",
                        "default": 20,
                    },
                },
            },
        ),
        Tool(
            name=MCPToolEnum.SEARCH_DOCUMENTATION.value,
            description="Search markdown documentation files (README, guides, etc.)",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for documentation content",
                    },
                    "repository_id": {
                        "type": "integer",
                        "description": "Optional repository ID to filter by",
                    },
                    "doc_type": {
                        "type": "string",
                        "description": "Filter by document type (readme, changelog, guide, api_doc)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name=MCPToolEnum.SEARCH_CONFIGURATION.value,
            description="Search configuration settings from appsettings.json and similar files",
            inputSchema={
                "type": "object",
                "properties": {
                    "key_pattern": {
                        "type": "string",
                        "description": "Configuration key pattern to search (e.g., 'Database:*', 'Logging:*')",
                    },
                    "repository_id": {
                        "type": "integer",
                        "description": "Optional repository ID to filter by",
                    },
                    "environment": {
                        "type": "string",
                        "description": "Filter by environment (development, staging, production, default)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 20)",
                        "default": 20,
                    },
                },
                "required": ["key_pattern"],
            },
        ),
        Tool(
            name=MCPToolEnum.LIST_DEPENDENCIES.value,
            description="List package dependencies from package.json, .csproj, etc.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repository_id": {
                        "type": "integer",
                        "description": "Repository ID to list dependencies for",
                    },
                    "dependency_type": {
                        "type": "string",
                        "description": "Filter by type (nuget, npm, pip, maven)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["repository_id"],
            },
        ),
        Tool(
            name=MCPToolEnum.GET_FILE_CONTENT.value,
            description="Read file content with line numbers and symbols",
            inputSchema={
                "type": "object",
                "properties": {
                    "repository_id": {
                        "type": "integer",
                        "description": "Repository ID",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to file within repository",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Optional start line (1-indexed)",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Optional end line (1-indexed)",
                    },
                },
                "required": ["repository_id", "file_path"],
            },
        ),
        Tool(
            name=MCPToolEnum.FIND_USAGES.value,
            description="Find all places where a symbol is used",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol_id": {
                        "type": "integer",
                        "description": "Symbol ID to find usages for",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["symbol_id"],
            },
        ),
        Tool(
            name=MCPToolEnum.FIND_IMPLEMENTATIONS.value,
            description="Find all classes that implement an interface",
            inputSchema={
                "type": "object",
                "properties": {
                    "interface_id": {
                        "type": "integer",
                        "description": "Interface symbol ID",
                    },
                },
                "required": ["interface_id"],
            },
        ),
        Tool(
            name=MCPToolEnum.FIND_REFERENCES.value,
            description="Find all references to a symbol (calls, inherits, implements)",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol_id": {
                        "type": "integer",
                        "description": "Symbol ID to find references for",
                    },
                    "reference_type": {
                        "type": "string",
                        "description": "Optional filter by type (calls, inherits, implements)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["symbol_id"],
            },
        ),
        Tool(
            name=MCPToolEnum.GET_FILE_TREE.value,
            description="Get directory tree structure of repository",
            inputSchema={
                "type": "object",
                "properties": {
                    "repository_id": {
                        "type": "integer",
                        "description": "Repository ID",
                    },
                    "path": {
                        "type": "string",
                        "description": "Optional path to start from (default: root)",
                        "default": "",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Maximum depth to traverse (default: 3)",
                        "default": 3,
                    },
                },
                "required": ["repository_id"],
            },
        ),
        Tool(
            name=MCPToolEnum.LIST_SYMBOLS_IN_FILE.value,
            description="List all symbols in a specific file",
            inputSchema={
                "type": "object",
                "properties": {
                    "repository_id": {
                        "type": "integer",
                        "description": "Repository ID",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Path to file within repository",
                    },
                    "symbol_kinds": {
                        "type": "array",
                        "description": "Optional filter by symbol kinds",
                        "items": {"type": "string"},
                    },
                },
                "required": ["repository_id", "file_path"],
            },
        ),
        Tool(
            name=MCPToolEnum.FIND_API_ENDPOINTS.value,
            description="Find all API endpoints in repository (ASP.NET Core Web API)",
            inputSchema={
                "type": "object",
                "properties": {
                    "repository_id": {
                        "type": "integer",
                        "description": "Repository ID",
                    },
                    "http_method": {
                        "type": "string",
                        "description": "Optional filter by HTTP method (GET, POST, PUT, DELETE, PATCH)",
                    },
                    "route_pattern": {
                        "type": "string",
                        "description": "Optional filter by route pattern (supports wildcards like '/api/users/*')",
                    },
                },
                "required": ["repository_id"],
            },
        ),
        Tool(
            name=MCPToolEnum.GET_CALL_HIERARCHY.value,
            description="Get call hierarchy tree showing what a function calls or what calls it",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol_id": {
                        "type": "integer",
                        "description": "Symbol ID to get call hierarchy for",
                    },
                    "direction": {
                        "type": "string",
                        "description": "Direction: 'outbound' (what it calls) or 'inbound' (what calls it)",
                        "default": "outbound",
                    },
                    "depth": {
                        "type": "integer",
                        "description": "Maximum depth to traverse (default: 3)",
                        "default": 3,
                    },
                },
                "required": ["symbol_id"],
            },
        ),
        Tool(
            name=MCPToolEnum.FIND_CALLERS.value,
            description="Find all symbols that call this function/method",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol_id": {
                        "type": "integer",
                        "description": "Symbol ID to find callers for",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["symbol_id"],
            },
        ),
        Tool(
            name=MCPToolEnum.FIND_CALLEES.value,
            description="Find all functions/methods that this symbol calls",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol_id": {
                        "type": "integer",
                        "description": "Symbol ID to find callees for",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["symbol_id"],
            },
        ),
        Tool(
            name=MCPToolEnum.ANALYZE_ARCHITECTURE.value,
            description="Analyze repository architecture and detect design patterns",
            inputSchema={
                "type": "object",
                "properties": {
                    "repository_id": {
                        "type": "integer",
                        "description": "Repository ID to analyze",
                    },
                },
                "required": ["repository_id"],
            },
        ),
        Tool(
            name=MCPToolEnum.SEARCH_BY_PATH.value,
            description="Search for files by path pattern using wildcards",
            inputSchema={
                "type": "object",
                "properties": {
                    "repository_id": {
                        "type": "integer",
                        "description": "Repository ID to search in",
                    },
                    "path_pattern": {
                        "type": "string",
                        "description": "Path pattern with wildcards (e.g., '*/services/*.cs', 'components/**/*.tsx')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["repository_id", "path_pattern"],
            },
        ),
        Tool(
            name=MCPToolEnum.TRACE_REQUEST_FLOW.value,
            description="Trace complete request flow through application layers (Controller -> Service -> Repository)",
            inputSchema={
                "type": "object",
                "properties": {
                    "endpoint": {
                        "type": "string",
                        "description": "API endpoint to trace (e.g., 'POST /api/users')",
                    },
                    "repository_id": {
                        "type": "integer",
                        "description": "Repository ID",
                    },
                },
                "required": ["endpoint", "repository_id"],
            },
        ),
        Tool(
            name=MCPToolEnum.GET_PROJECT_MAP.value,
            description="Get hierarchical project map with annotations - provides instant overview of repository structure, purpose, and statistics (Phase 1: Exploration & Mapping)",
            inputSchema={
                "type": "object",
                "properties": {
                    "repository_id": {
                        "type": "integer",
                        "description": "Repository ID to generate map for",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum directory depth to traverse (default: 2, recommended: 2-3 for quick overview)",
                        "default": 2,
                    },
                },
                "required": ["repository_id"],
            },
        ),
        Tool(
            name=MCPToolEnum.GET_MODULE_SUMMARY.value,
            description="Get AI-generated summary for a specific module - provides purpose, key components, dependencies, and entry points in a single view (Phase 2: Aggregated Context)",
            inputSchema={
                "type": "object",
                "properties": {
                    "repository_id": {
                        "type": "integer",
                        "description": "Repository ID",
                    },
                    "module_path": {
                        "type": "string",
                        "description": "Path to module (e.g., 'src/api', 'backend/auth', 'frontend/components')",
                    },
                    "generate_if_missing": {
                        "type": "boolean",
                        "description": "Generate summary on-demand if it doesn't exist (default: true)",
                        "default": True,
                    },
                },
                "required": ["repository_id", "module_path"],
            },
        ),
        Tool(
            name=MCPToolEnum.QUERY_CODEBASE_STRUCTURE.value,
            description="Query codebase structure using natural language (Phase 4: Text-to-SQL). Enables complex architectural queries like 'Find all controllers', 'List public methods without docs', 'Show methods with high complexity'. Translates natural language to SQL for deep structural analysis.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language query about code structure (e.g., 'Find all public methods in controllers', 'List undocumented classes', 'Show complex methods')",
                    },
                    "repository_id": {
                        "type": "integer",
                        "description": "Optional repository ID to limit search scope",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 50)",
                        "default": 50,
                        "minimum": 1,
                        "maximum": 200,
                    },
                },
                "required": ["query"],
            },
        ),
    ]


async def _list_mcp_resources() -> List[Dict[str, Any]]:
    """List available resources for HTTP transport."""
    try:
        async with get_async_session() as session:
            # Get repository statistics for resources
            result = await session.execute(select(Repository))
            repos = result.scalars().all()
            
            resources = []
            
            # Add repository overview resource
            resources.append({
                "uri": "axon://repositories/overview",
                "name": "Repository Overview",
                "description": "Overview of all indexed repositories with statistics",
                "mimeType": "application/json"
            })
            
            # Add individual repository resources
            for repo in repos:
                resources.append({
                    "uri": f"axon://repository/{repo.id}",
                    "name": f"Repository: {repo.name}",
                    "description": f"Detailed information about {repo.name} repository",
                    "mimeType": "application/json"
                })
                
                # Add repository file tree resource
                resources.append({
                    "uri": f"axon://repository/{repo.id}/files",
                    "name": f"Files: {repo.name}",
                    "description": f"File tree and structure of {repo.name}",
                    "mimeType": "application/json"
                })
            
            return resources
            
    except Exception as e:
        logger.error("mcp_list_resources_failed", error=str(e), exc_info=True)
        return []


async def _read_mcp_resource(uri: str) -> Dict[str, Any]:
    """Read a specific resource for HTTP transport."""
    try:
        async with get_async_session() as session:
            if uri == "axon://repositories/overview":
                # Return repository overview
                result = await session.execute(select(Repository))
                repos = result.scalars().all()
                
                overview = {
                    "total_repositories": len(repos),
                    "repositories": [
                        {
                            "id": repo.id,
                            "name": repo.name,
                            "status": repo.status.value,
                            "total_files": repo.total_files,
                            "total_symbols": repo.total_symbols,
                            "last_synced": repo.last_synced_at.isoformat() if repo.last_synced_at else None,
                            "url": repo.url,
                            "default_branch": repo.default_branch
                        }
                        for repo in repos
                    ]
                }
                
                return {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(overview, indent=2)
                }
                
            elif uri.startswith("axon://repository/") and uri.endswith("/files"):
                # Extract repository ID
                repo_id = int(uri.split("/")[2])
                
                # Get repository files
                result = await session.execute(
                    select(File, Repository)
                    .join(Repository, File.repository_id == Repository.id)
                    .where(Repository.id == repo_id)
                )
                files_data = result.all()
                
                if not files_data:
                    raise ValueError(f"Repository {repo_id} not found")
                
                repo_name = files_data[0][1].name if files_data else "Unknown"
                
                # Get symbol counts per file (since File model doesn't have symbol_count attribute)
                file_ids = [file.id for file, _ in files_data]
                symbol_counts_result = await session.execute(
                    select(
                        Symbol.file_id,
                        func.count(Symbol.id).label('count')
                    )
                    .where(Symbol.file_id.in_(file_ids))
                    .group_by(Symbol.file_id)
                ) if file_ids else None
                symbol_counts = {row.file_id: row.count for row in symbol_counts_result} if symbol_counts_result else {}
                
                file_tree = {
                    "repository_id": repo_id,
                    "repository_name": repo_name,
                    "total_files": len(files_data),
                    "files": [
                        {
                            "id": file.id,
                            "path": file.path,
                            "language": file.language.value if file.language else None,
                            "size_bytes": file.size_bytes,
                            "symbol_count": symbol_counts.get(file.id, 0),
                            "last_modified": file.last_modified.isoformat() if file.last_modified else None
                        }
                        for file, _ in files_data
                    ]
                }
                
                return {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(file_tree, indent=2)
                }
                
            elif uri.startswith("axon://repository/"):
                # Extract repository ID
                repo_id = int(uri.split("/")[2])
                
                # Get repository details
                result = await session.execute(
                    select(Repository).where(Repository.id == repo_id)
                )
                repo = result.scalar_one_or_none()
                
                if not repo:
                    raise ValueError(f"Repository {repo_id} not found")
                
                # Get file statistics by language
                files_result = await session.execute(
                    select(File).where(File.repository_id == repo_id)
                )
                files = files_result.scalars().all()
                
                # Get symbol counts per file (since File model doesn't have symbol_count attribute)
                file_ids = [f.id for f in files]
                symbol_counts_result = await session.execute(
                    select(
                        Symbol.file_id,
                        func.count(Symbol.id).label('count')
                    )
                    .where(Symbol.file_id.in_(file_ids))
                    .group_by(Symbol.file_id)
                ) if file_ids else None
                symbol_counts = {row.file_id: row.count for row in symbol_counts_result} if symbol_counts_result else {}
                
                language_stats = {}
                for file in files:
                    lang = file.language.value if file.language else "unknown"
                    if lang not in language_stats:
                        language_stats[lang] = {"files": 0, "symbols": 0}
                    language_stats[lang]["files"] += 1
                    language_stats[lang]["symbols"] += symbol_counts.get(file.id, 0)
                
                repo_details = {
                    "id": repo.id,
                    "name": repo.name,
                    "url": repo.url,
                    "default_branch": repo.default_branch,
                    "status": repo.status.value,
                    "total_files": repo.total_files,
                    "total_symbols": repo.total_symbols,
                    "last_synced": repo.last_synced_at.isoformat() if repo.last_synced_at else None,
                    "created_at": repo.created_at.isoformat(),
                    "language_statistics": language_stats,
                    "description": f"Repository containing {repo.total_files} files with {repo.total_symbols} code symbols"
                }
                
                return {
                    "uri": uri,
                    "mimeType": "application/json", 
                    "text": json.dumps(repo_details, indent=2)
                }
            else:
                raise ValueError(f"Unknown resource URI: {uri}")
                
    except Exception as e:
        logger.error("mcp_read_resource_failed", uri=uri, error=str(e), exc_info=True)
        return {
            "uri": uri,
            "mimeType": "text/plain",
            "text": f"Error reading resource: {str(e)}"
        }


async def _search_code(
    query: str,
    limit: int = 10,
    repository_name: Optional[str] = None,
    language: Optional[str] = None,
    symbol_kind: Optional[str] = None,
) -> List[TextContent]:
    """
    Search for code symbols across repositories.

    Args:
        query: Search query (function name, class name, or description)
        limit: Maximum number of results (default: 10, max: 50)
        repository_name: Filter by repository name
        language: Filter by programming language (csharp, javascript, typescript, vue)
        symbol_kind: Filter by symbol kind (function, class, method, etc.)

    Returns:
        List of matching code symbols with their locations and documentation
    """
    start_time = time.time()

    try:
        mcp_tool_calls_total.labels(tool_name="search_code", status="started").inc()

        async with get_async_session() as session:
            search_service = SearchService(session)

            # Convert string enums
            language_enum = LanguageEnum(language) if language else None
            symbol_kind_enum = SymbolKindEnum(symbol_kind) if symbol_kind else None

            # Get repository ID if name provided
            repository_id = None
            if repository_name:
                result = await session.execute(
                    select(Repository).where(Repository.name == repository_name)
                )
                # Use first() instead of scalar_one_or_none() to handle duplicate repo names
                repo = result.scalars().first()
                if repo:
                    repository_id = repo.id

            results = await search_service.search(
                query=query,
                limit=min(limit, 50),
                repository_id=repository_id,
                language=language_enum,
                symbol_kind=symbol_kind_enum,
                hybrid=True,
            )

            # Format results for ChatGPT with IDs for cross-referencing
            formatted_results = []
            for result in results:
                formatted_results.append(
                    {
                        # IDs for drilling down (ENHANCED)
                        "symbol_id": result.symbol_id,
                        "file_id": result.file_id,
                        "repository_id": result.repository_id,
                        # Symbol info
                        "name": result.name,
                        "kind": result.kind.value,
                        "signature": result.signature,
                        "fully_qualified_name": result.fully_qualified_name,
                        # Location
                        "file": result.file_path,
                        "repository": result.repository_name,
                        "lines": f"{result.start_line}-{result.end_line}",
                        # Code content (ENHANCED)
                        "code_snippet": result.code_snippet,
                        "documentation": result.documentation
                        or "No documentation available",
                         # Search metadata
                        "relevance_score": round(result.score, 3),
                        "match_type": result.match_type,
                        # Quick access (ENHANCED)
                        "context_url": result.context_url,
                    }
                )

            duration = time.time() - start_time
            mcp_tool_duration.labels(tool_name="search_code").observe(duration)
            mcp_tool_calls_total.labels(
                tool_name="search_code", status="success"
            ).inc()

            formatter = await _get_formatter()
            return [
                TextContent(
                    type="text",
                    text=formatter._format_search_results(formatted_results, query),
                )
            ]

    except Exception as e:
        logger.error("mcp_search_failed", error=str(e), exc_info=True)
        mcp_tool_calls_total.labels(tool_name="search_code", status="error").inc()

        return [TextContent(type="text", text=f"Search failed: {str(e)}")]


async def _get_symbol_context(
    symbol_id: int,
    include_relationships: bool = True,
    depth: int = 0,
    direction: str = "downstream",
    max_symbols: int = 50,
    relation_types: Optional[List[str]] = None,
) -> List[TextContent]:
    """
    Get detailed context for a specific symbol with recursive call graph traversal.
    
    Phase 3 Enhancement: Now supports multi-level traversal to show call chains,
    inheritance hierarchies, and dependency flows.

    Args:
        symbol_id: ID of the symbol
        include_relationships: Include direct relationships (for backward compatibility)
        depth: Traversal depth (0=no traversal, 1=direct, 2+=recursive, max: 5)
        direction: Traversal direction ('downstream', 'upstream', 'both')
        max_symbols: Maximum symbols to include (1-100)
        relation_types: Relationship types to follow (default: CALLS, INHERITS, IMPLEMENTS, USES)

    Returns:
        Symbol context with full code for root, signatures for related symbols
    """
    # Validate required parameters
    if symbol_id is None:
        return [
            TextContent(
                type="text",
                text="❌ Missing required parameter: symbol_id\n\n"
                "💡 Use `search_code(query)` to find symbols and get their IDs."
            )
        ]
    
    start_time = time.time()
    
    try:
        async with get_async_session() as session:
            # Validate and cap depth
            depth = max(0, min(depth, 5))
            max_symbols = max(1, min(max_symbols, 100))
            
            # Convert direction string to enum
            try:
                traversal_direction = TraversalDirection(direction.lower())
            except ValueError:
                traversal_direction = TraversalDirection.DOWNSTREAM
            
            # Convert relation_types strings to enums
            relation_type_enums = None
            if relation_types:
                relation_type_enums = []
                for rel_type_str in relation_types:
                    try:
                        relation_type_enums.append(RelationTypeEnum[rel_type_str])
                    except KeyError:
                        logger.warning(f"Invalid relation type: {rel_type_str}, skipping")
            
            # If depth > 0, use the new call graph traversal
            if depth > 0:
                logger.info(
                    "mcp_symbol_context_traversal_started",
                    symbol_id=symbol_id,
                    depth=depth,
                    direction=direction,
                    max_symbols=max_symbols,
                    relation_types=relation_types,
                )
                
                # Create traverser and config
                traverser = CallGraphTraverser(session)
                config = TraversalConfig(
                    depth=depth,
                    direction=traversal_direction,
                    max_symbols=max_symbols,
                    max_tokens=10000,
                    include_source_code=True,
                    include_signatures=True,
                )
                
                # Override default relation types if provided
                if relation_type_enums:
                    config.relation_types = relation_type_enums
                
                # Perform traversal
                result = await traverser.traverse(symbol_id, config)
                
                if not result:
                    return [TextContent(type="text", text="Symbol not found")]
                
                # Format using new traversal formatter
                formatted_text = traverser.format_result_markdown(result, include_stats=True)
                
                duration = time.time() - start_time
                mcp_tool_duration.labels(tool="get_symbol_context").observe(duration)
                mcp_tool_calls_total.labels(tool="get_symbol_context", status="success").inc()
                
                logger.info(
                    "mcp_symbol_context_traversal_complete",
                    symbol_id=symbol_id,
                    total_symbols=result.total_symbols,
                    depth_reached=result.max_depth_reached,
                    duration=duration,
                )
                
                return [TextContent(type="text", text=formatted_text)]
            
            # Original implementation for depth=0 (backward compatibility)
            else:
                # Get symbol with file and repository info
                result = await session.execute(
                    select(Symbol, File, Repository)
                    .join(File, Symbol.file_id == File.id)
                    .join(Repository, File.repository_id == Repository.id)
                    .where(Symbol.id == symbol_id)
                )
                row = result.first()

                if not row:
                    return [TextContent(type="text", text="Symbol not found")]

                symbol, file, repo = row

                # Build context with IDs for cross-referencing
                context = {
                    "symbol": {
                        # IDs (ENHANCED)
                        "id": symbol.id,
                        "file_id": file.id,
                        "repository_id": repo.id,
                        "parent_symbol_id": symbol.parent_symbol_id,
                        # Symbol details
                        "name": symbol.name,
                        "kind": symbol.kind.value,
                        "fully_qualified_name": symbol.fully_qualified_name,
                        "signature": symbol.signature,
                        "documentation": symbol.documentation,
                        "parameters": symbol.parameters,
                        "return_type": symbol.return_type,
                        "complexity": symbol.complexity,
                        "access_modifier": symbol.access_modifier.value
                        if symbol.access_modifier
                        else None,
                    },
                    "location": {
                        "repository": repo.name,
                        "repository_id": repo.id,
                        "file": file.path,
                        "file_id": file.id,
                        "lines": f"{symbol.start_line}-{symbol.end_line}",
                        "language": file.language.value,
                    },
                }

                # Get symbol source code from chunks
                chunk_result = await session.execute(
                    select(Chunk.content)
                    .where(Chunk.symbol_id == symbol_id)
                    .order_by(Chunk.id)
                    .limit(1)  # Get the main body chunk
                )
                chunk_row = chunk_result.first()
                if chunk_row:
                    context["source_code"] = chunk_row[0]

                # Add relationships if requested
                if include_relationships:
                    # Get outgoing relationships (from this symbol)
                    relations_from_result = await session.execute(
                        select(Relation, Symbol)
                        .join(Symbol, Relation.to_symbol_id == Symbol.id)
                        .where(Relation.from_symbol_id == symbol_id)
                    )
                    relations_from = relations_from_result.all()

                    # Get incoming relationships (to this symbol)
                    relations_to_result = await session.execute(
                        select(Relation, Symbol)
                        .join(Symbol, Relation.from_symbol_id == Symbol.id)
                        .where(Relation.to_symbol_id == symbol_id)
                    )
                    relations_to = relations_to_result.all()

                    # Organize by relationship type
                    calls = []
                    called_by = []
                    inherits_from = []
                    inherited_by = []

                    for relation, related_symbol in relations_from:
                        rel_info = {
                            "name": related_symbol.name,
                            "id": related_symbol.id,
                            "kind": related_symbol.kind.value,
                        }
                        if relation.relation_type == RelationTypeEnum.CALLS:
                            calls.append(rel_info)
                        elif relation.relation_type == RelationTypeEnum.INHERITS:
                            inherits_from.append(rel_info)

                    for relation, related_symbol in relations_to:
                        rel_info = {
                            "name": related_symbol.name,
                            "id": related_symbol.id,
                            "kind": related_symbol.kind.value,
                        }
                        if relation.relation_type == RelationTypeEnum.CALLS:
                            called_by.append(rel_info)
                        elif relation.relation_type == RelationTypeEnum.INHERITS:
                            inherited_by.append(rel_info)

                    context["relationships"] = {
                        "calls": calls,
                        "called_by": called_by,
                        "inherits_from": inherits_from,
                        "inherited_by": inherited_by,
                    }

                # Get connected endpoints (Phase 3: The Linker)
                try:
                    connected = await get_connected_endpoints_for_symbol(session, symbol_id)
                    if any(connected.values()):
                        context["connected_endpoints"] = connected
                except Exception as e:
                    logger.warning(
                        "connected_endpoints_fetch_failed",
                        symbol_id=symbol_id,
                        error=str(e)
                    )

                formatter = await _get_formatter()
                
                duration = time.time() - start_time
                mcp_tool_duration.labels(tool="get_symbol_context").observe(duration)
                mcp_tool_calls_total.labels(tool="get_symbol_context", status="success").inc()
                
                return [
                    TextContent(
                        type="text",
                        text=formatter._format_symbol_context(context),
                    )
                ]

    except Exception as e:
        logger.error("mcp_get_symbol_context_failed", error=str(e), exc_info=True)
        mcp_tool_calls_total.labels(tool="get_symbol_context", status="error").inc()
        return [
            TextContent(
                type="text",
                text=f"Failed to get symbol context: {str(e)}",
            )
        ]


async def _search_documentation(
    query: str,
    repository_id: Optional[int] = None,
    doc_type: Optional[str] = None,
    limit: int = 10,
) -> List[TextContent]:
    """
    Search markdown documentation files.

    Args:
        query: Search query
        repository_id: Optional repository ID filter
        doc_type: Optional document type filter
        limit: Maximum results

    Returns:
        List of matching documentation sections
    """
    try:
        async with get_async_session() as session:
            # Search in Symbol table for DOCUMENT_SECTION and CODE_EXAMPLE kinds
            from sqlalchemy import or_, and_
            
            filters = [
                Symbol.kind.in_([SymbolKindEnum.DOCUMENT_SECTION, SymbolKindEnum.CODE_EXAMPLE])
            ]
            
            # Add text search filters
            search_filters = [
                Symbol.name.ilike(f"%{query}%"),
                Symbol.documentation.ilike(f"%{query}%"),
                Symbol.signature.ilike(f"%{query}%"),
            ]
            filters.append(or_(*search_filters))
            
            # Add repository filter
            if repository_id:
                filters.append(File.repository_id == repository_id)
            
            query_stmt = (
                select(Symbol, File, Repository)
                .join(File, Symbol.file_id == File.id)
                .join(Repository, File.repository_id == Repository.id)
                .where(and_(*filters))
                .limit(limit)
            )
            
            result = await session.execute(query_stmt)
            rows = result.all()
            
            if not rows:
                return [
                    TextContent(
                        type="text",
                        text=f"No documentation found for query: '{query}'",
                    )
                ]
            
            # Format results
            formatted = [f"Found {len(rows)} documentation sections for '{query}':\n\n"]
            
            for symbol, file, repo in rows:
                formatted.append(
                    f"## {symbol.name}\n"
                    f"**Repository**: {repo.name}\n"
                    f"**File**: {file.path} (line {symbol.start_line})\n"
                    f"**Type**: {symbol.kind.value}\n\n"
                )
                
                if symbol.documentation:
                    doc_preview = symbol.documentation[:300]
                    if len(symbol.documentation) > 300:
                        doc_preview += "..."
                    formatted.append(f"{doc_preview}\n\n")
                
                formatted.append("---\n\n")
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_search_documentation_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to search documentation: {str(e)}",
            )
        ]


async def _search_configuration(
    key_pattern: str,
    repository_id: Optional[int] = None,
    environment: Optional[str] = None,
    limit: int = 20,
) -> List[TextContent]:
    """
    Search configuration get_settings().

    Args:
        key_pattern: Configuration key pattern (supports wildcards like 'Database:*')
        repository_id: Optional repository ID filter
        environment: Optional environment filter
        limit: Maximum results

    Returns:
        List of matching configuration entries
    """
    try:
        async with get_async_session() as session:
            from sqlalchemy import and_
            
            filters = []
            
            # Convert wildcard pattern to SQL LIKE pattern
            like_pattern = key_pattern.replace('*', '%')
            filters.append(Symbol.name.ilike(like_pattern))
            
            # Filter by structured_docs type=configuration
            filters.append(Symbol.structured_docs['type'].astext == 'configuration')
            
            # Add repository filter
            if repository_id:
                filters.append(File.repository_id == repository_id)
            
            # Add environment filter
            if environment:
                filters.append(Symbol.structured_docs['environment'].astext == environment)
            
            query_stmt = (
                select(Symbol, File, Repository)
                .join(File, Symbol.file_id == File.id)
                .join(Repository, File.repository_id == Repository.id)
                .where(and_(*filters))
                .limit(limit)
            )
            
            result = await session.execute(query_stmt)
            rows = result.all()
            
            if not rows:
                return [
                    TextContent(
                        type="text",
                        text=f"No configuration found for pattern: '{key_pattern}'",
                    )
                ]
            
            # Format results
            formatted = [f"Found {len(rows)} configuration settings matching '{key_pattern}':\n\n"]
            
            for symbol, file, repo in rows:
                docs = symbol.structured_docs or {}
                is_secret = docs.get('is_secret', False)
                value = docs.get('value', 'N/A')
                if is_secret:
                    value = '[REDACTED]'
                
                formatted.append(
                    f"**{symbol.name}** {'🔒' if is_secret else ''}\n"
                    f"Repository: {repo.name}\n"
                    f"File: {file.path}\n"
                    f"Environment: {docs.get('environment', 'default')}\n"
                    f"Type: {docs.get('value_type', 'unknown')}\n"
                    f"Value: `{value}`\n\n"
                    "---\n\n"
                )
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_search_configuration_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to search configuration: {str(e)}",
            )
        ]


async def _list_dependencies(
    repository_id: int,
    dependency_type: Optional[str] = None,
    limit: int = 50,
) -> List[TextContent]:
    """
    List package dependencies.

    Args:
        repository_id: Repository ID
        dependency_type: Optional type filter (nuget, npm, etc.)
        limit: Maximum results

    Returns:
        List of dependencies
    """
    try:
        async with get_async_session() as session:
            from sqlalchemy import and_
            
            filters = [
                Symbol.structured_docs['type'].astext.in_(['nuget_package', 'npm_package'])
            ]
            
            # Add repository filter
            filters.append(File.repository_id == repository_id)
            
            # Add dependency type filter
            if dependency_type:
                if dependency_type.lower() == 'nuget':
                    filters.append(Symbol.structured_docs['type'].astext == 'nuget_package')
                elif dependency_type.lower() == 'npm':
                    filters.append(Symbol.structured_docs['type'].astext == 'npm_package')
            
            query_stmt = (
                select(Symbol, File, Repository)
                .join(File, Symbol.file_id == File.id)
                .join(Repository, File.repository_id == Repository.id)
                .where(and_(*filters))
                .limit(limit)
            )
            
            result = await session.execute(query_stmt)
            rows = result.all()
            
            if not rows:
                return [
                    TextContent(
                        type="text",
                        text=f"No dependencies found for repository ID {repository_id}",
                    )
                ]
            
            # Group by type
            nuget_deps = []
            npm_deps = []
            
            for symbol, file, repo in rows:
                docs = symbol.structured_docs or {}
                dep_type = docs.get('type', '')
                version = docs.get('version', 'unknown')
                is_dev = docs.get('is_dev_dependency', False)
                
                dep_info = f"- **{symbol.name}** v{version}{' (dev)' if is_dev else ''} - {file.path}\n"
                
                if dep_type == 'nuget_package':
                    nuget_deps.append(dep_info)
                elif dep_type == 'npm_package':
                    npm_deps.append(dep_info)
            
            # Format results
            formatted = [f"Dependencies for repository: **{rows[0][2].name}**\n\n"]
            
            if nuget_deps:
                formatted.append(f"### NuGet Packages ({len(nuget_deps)})\n\n")
                formatted.extend(nuget_deps)
                formatted.append("\n")
            
            if npm_deps:
                formatted.append(f"### NPM Packages ({len(npm_deps)})\n\n")
                formatted.extend(npm_deps)
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_list_dependencies_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to list dependencies: {str(e)}",
            )
        ]


async def _get_file_content(
    repository_id: int,
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> List[TextContent]:
    """
    Read file content with line numbers.

    Args:
        repository_id: Repository ID
        file_path: Path to file within repository
        start_line: Optional start line (1-indexed)
        end_line: Optional end line (1-indexed)

    Returns:
        File content with line numbers and symbols
    """
    try:
        async with get_async_session() as session:
            from pathlib import Path as FilePath
            
            # Get repository
            result = await session.execute(
                select(Repository).where(Repository.id == repository_id)
            )
            repo = result.scalar_one_or_none()
            
            if not repo:
                return [TextContent(type="text", text=f"Repository ID {repository_id} not found")]
            
            # Get file record
            result = await session.execute(
                select(File).where(
                    File.repository_id == repository_id,
                    File.path == file_path
                )
            )
            file_record = result.scalar_one_or_none()
            
            if not file_record:
                return [TextContent(type="text", text=f"File '{file_path}' not found in repository")]
            
            # Try to read file content from disk
            # Construct file path from repository cache
            from src.gitlab.repository_manager import RepositoryManager
            from src.azuredevops.repository_manager import AzureDevOpsRepositoryManager
            
            # Select appropriate repository manager based on provider
            if repo.provider == SourceControlProviderEnum.GITLAB:
                repo_manager = RepositoryManager()
                repo_path = repo_manager.cache_dir / repo.path_with_namespace.replace("/", "_")
            elif repo.provider == SourceControlProviderEnum.AZUREDEVOPS:
                repo_manager = AzureDevOpsRepositoryManager()
                if not repo.azuredevops_project_name:
                    return [TextContent(type="text", text=f"Azure DevOps project name not set for repository {repository_id}")]
                repo_path = repo_manager.get_repository_path(repo.azuredevops_project_name, repo.name)
            elif repo.provider == SourceControlProviderEnum.GITHUB:
                from src.github.repository_manager import GitHubRepositoryManager
                repo_manager = GitHubRepositoryManager()
                repo_path = repo_manager.cache_dir / repo.path_with_namespace.replace("/", "_")
            else:
                return [TextContent(type="text", text=f"Unsupported provider: {repo.provider}")]
            
            full_file_path = repo_path / file_path
            
            if not full_file_path.exists():
                return [TextContent(type="text", text=f"File not found on disk: {file_path}")]
            
            # Read file content
            with open(full_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            # Apply line range if specified
            if start_line is not None:
                start_idx = max(0, start_line - 1)
            else:
                start_idx = 0
            
            if end_line is not None:
                end_idx = min(len(lines), end_line)
            else:
                end_idx = len(lines)
            
            # Format with line numbers
            numbered_lines = []
            for i, line in enumerate(lines[start_idx:end_idx], start=start_idx + 1):
                numbered_lines.append(f"{i:6d}| {line.rstrip()}")
            
            content = '\n'.join(numbered_lines)
            
            # Get symbols in this file
            result = await session.execute(
                select(Symbol).where(Symbol.file_id == file_record.id).order_by(Symbol.start_line)
            )
            symbols = result.scalars().all()
            
            # Format response
            formatted = [
                f"# {file_path}\n",
                f"Repository: **{repo.name}**\n",
                f"Language: {file_record.language.value}\n",
                f"Total Lines: {len(lines)}\n",
                f"Symbols: {len(symbols)}\n\n",
                "## Content:\n\n",
                f"```{file_record.language.value}\n",
                content,
                "\n```\n\n",
                "## Symbols in this file:\n\n"
            ]
            
            for symbol in symbols:
                formatted.append(
                    f"- **{symbol.name}** ({symbol.kind.value}) - Line {symbol.start_line}\n"
                )
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_get_file_content_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to get file content: {str(e)}",
            )
        ]


async def _find_usages(
    symbol_id: int,
    limit: int = 50,
) -> List[TextContent]:
    """
    Find all places where a symbol is used.

    Args:
        symbol_id: Symbol ID to find usages for
        limit: Maximum results

    Returns:
        List of usages
    """
    try:
        async with get_async_session() as session:
            # Get the symbol
            result = await session.execute(
                select(Symbol).where(Symbol.id == symbol_id)
            )
            symbol = result.scalar_one_or_none()
            
            if not symbol:
                return [TextContent(type="text", text=f"Symbol ID {symbol_id} not found")]
            
            # Find relationships where this symbol is called/used
            result = await session.execute(
                select(Relation, Symbol, File)
                .join(Symbol, Relation.from_symbol_id == Symbol.id)
                .join(File, Symbol.file_id == File.id)
                .where(Relation.to_symbol_id == symbol_id)
                .limit(limit)
            )
            usages = result.all()
            
            if not usages:
                return [TextContent(type="text", text=f"No usages found for '{symbol.name}'")]
            
            # Format results
            formatted = [
                f"Found {len(usages)} usages of **{symbol.name}** ({symbol.kind.value}):\n\n"
            ]
            
            for relation, using_symbol, file in usages:
                formatted.append(
                    f"- **{using_symbol.name}** ({using_symbol.kind.value})\n"
                    f"  File: {file.path}\n"
                    f"  Line: {using_symbol.start_line}\n"
                    f"  Type: {relation.relation_type.value}\n\n"
                )
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_find_usages_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to find usages: {str(e)}",
            )
        ]


async def _find_implementations(
    interface_id: int,
) -> List[TextContent]:
    """
    Find all classes that implement an interface.

    Args:
        interface_id: Interface symbol ID

    Returns:
        List of implementations
    """
    try:
        async with get_async_session() as session:
            # Get the interface
            result = await session.execute(
                select(Symbol).where(Symbol.id == interface_id)
            )
            interface = result.scalar_one_or_none()
            
            if not interface:
                return [TextContent(type="text", text=f"Interface ID {interface_id} not found")]
            
            # Find implementations
            result = await session.execute(
                select(Symbol, File)
                .join(Relation, Relation.from_symbol_id == Symbol.id)
                .join(File, Symbol.file_id == File.id)
                .where(
                    Relation.to_symbol_id == interface_id,
                    Relation.relation_type == RelationTypeEnum.IMPLEMENTS
                )
            )
            implementations = result.all()
            
            if not implementations:
                return [TextContent(type="text", text=f"No implementations found for '{interface.name}'")]
            
            # Format results
            formatted = [
                f"Found {len(implementations)} implementations of **{interface.name}**:\n\n"
            ]
            
            for impl_symbol, file in implementations:
                formatted.append(
                    f"- **{impl_symbol.name}** ({impl_symbol.kind.value})\n"
                    f"  File: {file.path}\n"
                    f"  Line: {impl_symbol.start_line}\n\n"
                )
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_find_implementations_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to find implementations: {str(e)}",
            )
        ]


async def _find_references(
    symbol_id: int,
    reference_type: Optional[str] = None,
    limit: int = 50,
) -> List[TextContent]:
    """
    Find all references to a symbol.

    Args:
        symbol_id: Symbol ID
        reference_type: Optional filter by type
        limit: Maximum results

    Returns:
        List of references
    """
    try:
        async with get_async_session() as session:
            from sqlalchemy import and_
            
            # Get the symbol
            result = await session.execute(
                select(Symbol).where(Symbol.id == symbol_id)
            )
            symbol = result.scalar_one_or_none()
            
            if not symbol:
                return [TextContent(type="text", text=f"Symbol ID {symbol_id} not found")]
            
            # Build query filters
            filters = [Relation.to_symbol_id == symbol_id]
            
            if reference_type:
                try:
                    rel_type = RelationTypeEnum(reference_type.lower())
                    filters.append(Relation.relation_type == rel_type)
                except ValueError:
                    pass
            
            # Find all references
            result = await session.execute(
                select(Relation, Symbol, File)
                .join(Symbol, Relation.from_symbol_id == Symbol.id)
                .join(File, Symbol.file_id == File.id)
                .where(and_(*filters))
                .limit(limit)
            )
            references = result.all()
            
            if not references:
                return [TextContent(type="text", text=f"No references found for '{symbol.name}'")]
            
            # Group by reference type
            by_type = {}
            for relation, ref_symbol, file in references:
                rel_type = relation.relation_type.value
                if rel_type not in by_type:
                    by_type[rel_type] = []
                by_type[rel_type].append((ref_symbol, file))
            
            # Format results
            formatted = [
                f"Found {len(references)} references to **{symbol.name}** ({symbol.kind.value}):\n\n"
            ]
            
            for rel_type, refs in by_type.items():
                formatted.append(f"### {rel_type.upper()} ({len(refs)})\n\n")
                for ref_symbol, file in refs:
                    formatted.append(
                        f"- **{ref_symbol.name}** ({ref_symbol.kind.value})\n"
                        f"  File: {file.path}\n"
                        f"  Line: {ref_symbol.start_line}\n\n"
                    )
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_find_references_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to find references: {str(e)}",
            )
        ]


async def _get_file_tree(
    repository_id: int,
    path: str = "",
    depth: int = 3,
) -> List[TextContent]:
    """
    Get directory tree structure.

    Args:
        repository_id: Repository ID
        path: Optional path to start from
        depth: Maximum depth to traverse

    Returns:
        Directory tree
    """
    # Validate required parameters
    if repository_id is None:
        return [
            TextContent(
                type="text",
                text="❌ Missing required parameter: repository_id\n\n"
                "💡 Use `list_repositories()` to find available repositories and their IDs."
            )
        ]
    
    try:
        async with get_async_session() as session:
            # Get repository
            result = await session.execute(
                select(Repository).where(Repository.id == repository_id)
            )
            repo = result.scalar_one_or_none()
            
            if not repo:
                return [TextContent(type="text", text=f"Repository ID {repository_id} not found")]
            
            # Get all files in repository
            result = await session.execute(
                select(File).where(File.repository_id == repository_id).order_by(File.path)
            )
            files = result.scalars().all()
            
            # Get symbol counts per file (since File model doesn't have symbol_count attribute)
            file_ids = [f.id for f in files]
            symbol_counts_result = await session.execute(
                select(
                    Symbol.file_id,
                    func.count(Symbol.id).label('count')
                )
                .where(Symbol.file_id.in_(file_ids))
                .group_by(Symbol.file_id)
            ) if file_ids else None
            symbol_counts = {row.file_id: row.count for row in symbol_counts_result} if symbol_counts_result else {}
            
            # Build tree structure
            tree = {}
            start_path = path.rstrip('/')
            file_to_symbol_count = {}  # Map file path to symbol count
            
            for file in files:
                # Filter by starting path
                if start_path and not file.path.startswith(start_path):
                    continue
                
                parts = file.path.split('/')
                current = tree
                
                for part in parts[:-1]:  # directories
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                
                # Add file with its symbol count
                file_to_symbol_count[file.path] = symbol_counts.get(file.id, 0)
                current[parts[-1]] = file
            
            # Format tree
            def format_tree(node, indent=0, max_depth=depth):
                if indent >= max_depth:
                    return []
                
                lines = []
                items = sorted(node.items())
                
                for name, value in items:
                    prefix = "  " * indent
                    if isinstance(value, dict):
                        # Directory
                        file_count = sum(1 for v in value.values() if isinstance(v, File))
                        lines.append(f"{prefix}📁 **{name}/** ({file_count} files)\n")
                        lines.extend(format_tree(value, indent + 1, max_depth))
                    else:
                        # File
                        file_obj = value
                        sym_count = file_to_symbol_count.get(file_obj.path, 0)
                        lines.append(
                            f"{prefix}📄 {name} ({file_obj.language.value}, {sym_count} symbols)\n"
                        )
                
                return lines
            
            formatted = [
                f"# File Tree: {repo.name}\n",
                f"Path: {'/' if not start_path else start_path}\n",
                f"Total Files: {len(files)}\n\n"
            ]
            formatted.extend(format_tree(tree))
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_get_file_tree_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to get file tree: {str(e)}",
            )
        ]


async def _list_symbols_in_file(
    repository_id: int,
    file_path: str,
    symbol_kinds: Optional[List[str]] = None,
) -> List[TextContent]:
    """
    List all symbols in a specific file.

    Args:
        repository_id: Repository ID
        file_path: Path to file
        symbol_kinds: Optional filter by kinds

    Returns:
        List of symbols
    """
    try:
        async with get_async_session() as session:
            from sqlalchemy import and_
            
            # Get file record
            result = await session.execute(
                select(File).where(
                    File.repository_id == repository_id,
                    File.path == file_path
                )
            )
            file_record = result.scalar_one_or_none()
            
            if not file_record:
                return [TextContent(type="text", text=f"File '{file_path}' not found in repository")]
            
            # Build filters
            filters = [Symbol.file_id == file_record.id]
            
            if symbol_kinds:
                try:
                    kinds = [SymbolKindEnum(k) for k in symbol_kinds]
                    filters.append(Symbol.kind.in_(kinds))
                except ValueError:
                    pass  # Invalid kind, ignore
            
            # Get symbols
            result = await session.execute(
                select(Symbol).where(and_(*filters)).order_by(Symbol.start_line)
            )
            symbols = result.scalars().all()
            
            if not symbols:
                return [TextContent(type="text", text=f"No symbols found in '{file_path}'")]
            
            # Group by kind
            by_kind = {}
            for symbol in symbols:
                kind = symbol.kind.value
                if kind not in by_kind:
                    by_kind[kind] = []
                by_kind[kind].append(symbol)
            
            # Format results
            formatted = [
                f"# Symbols in {file_path}\n",
                f"Total: {len(symbols)} symbols\n\n"
            ]
            
            for kind, syms in sorted(by_kind.items()):
                formatted.append(f"### {kind.upper()} ({len(syms)})\n\n")
                for symbol in syms:
                    formatted.append(
                        f"- **{symbol.name}** (Line {symbol.start_line})\n"
                    )
                    if symbol.signature:
                        formatted.append(f"  ```\n  {symbol.signature}\n  ```\n")
                    if symbol.documentation:
                        doc_preview = symbol.documentation[:100]
                        formatted.append(f"  {doc_preview}{'...' if len(symbol.documentation) > 100 else ''}\n")
                    formatted.append("\n")
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_list_symbols_in_file_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to list symbols: {str(e)}",
            )
        ]


async def _find_api_endpoints(
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
            from src.extractors.api_extractor import ApiEndpointExtractor
            
            # Extract endpoints
            extractor = ApiEndpointExtractor(session)
            endpoints = await extractor.extract_endpoints(repository_id)
            
            # Apply filters
            if http_method:
                endpoints = [e for e in endpoints if e.http_method.upper() == http_method.upper()]
            
            if route_pattern:
                # Convert wildcard pattern to regex
                import re
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


async def _get_call_hierarchy(
    symbol_id: int,
    direction: str = "outbound",
    depth: int = 3,
) -> List[TextContent]:
    """
    Get call hierarchy tree.

    Args:
        symbol_id: Symbol ID
        direction: 'outbound' (callees) or 'inbound' (callers)
        depth: Maximum depth

    Returns:
        Call hierarchy tree
    """
    try:
        async with get_async_session() as session:
            # Get the symbol
            result = await session.execute(
                select(Symbol).where(Symbol.id == symbol_id)
            )
            symbol = result.scalar_one_or_none()
            
            if not symbol:
                return [TextContent(type="text", text=f"Symbol ID {symbol_id} not found")]
            
            # Build hierarchy
            hierarchy = await _build_call_hierarchy_tree(
                session,
                symbol_id,
                direction,
                depth,
                visited=set()
            )
            
            # Format results
            formatted = [
                f"# Call Hierarchy for {symbol.name} ({direction})\n\n"
            ]
            formatted.append(_format_hierarchy_tree(hierarchy, symbol.name, 0))
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_get_call_hierarchy_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to get call hierarchy: {str(e)}",
            )
        ]


async def _build_call_hierarchy_tree(
    session: AsyncSession,
    symbol_id: int,
    direction: str,
    max_depth: int,
    current_depth: int = 0,
    visited: Optional[set] = None
) -> Dict[str, Any]:
    """Build hierarchical call tree."""
    if visited is None:
        visited = set()
    
    if current_depth >= max_depth or symbol_id in visited:
        return {}
    
    visited.add(symbol_id)
    
    # Get symbol info
    result = await session.execute(
        select(Symbol, File).join(File, Symbol.file_id == File.id).where(Symbol.id == symbol_id)
    )
    row = result.first()
    if not row:
        return {}
    
    symbol, file = row
    
    # Get relationships based on direction
    if direction == "outbound":
        # What does this symbol call?
        result = await session.execute(
            select(Relation, Symbol)
            .join(Symbol, Relation.to_symbol_id == Symbol.id)
            .where(
                Relation.from_symbol_id == symbol_id,
                Relation.relation_type == RelationTypeEnum.CALLS
            )
        )
    else:
        # What calls this symbol?
        result = await session.execute(
            select(Relation, Symbol)
            .join(Symbol, Relation.from_symbol_id == Symbol.id)
            .where(
                Relation.to_symbol_id == symbol_id,
                Relation.relation_type == RelationTypeEnum.CALLS
            )
        )
    
    children = []
    for relation, related_symbol in result.all():
        child_tree = await _build_call_hierarchy_tree(
            session,
            related_symbol.id,
            direction,
            max_depth,
            current_depth + 1,
            visited
        )
        children.append({
            'symbol': related_symbol,
            'children': child_tree
        })
    
    return {
        'symbol': symbol,
        'file': file,
        'children': children
    }


def _format_hierarchy_tree(tree: Dict[str, Any], root_name: str, indent: int = 0) -> str:
    """Format call hierarchy tree as text."""
    if not tree or 'symbol' not in tree:
        return ""
    
    lines = []
    symbol = tree['symbol']
    file = tree.get('file')
    prefix = "  " * indent
    
    if indent == 0:
        lines.append(f"{prefix}**{root_name}** ({symbol.kind.value})\n")
    else:
        lines.append(
            f"{prefix}└─ {symbol.name} ({symbol.kind.value}) - {file.path if file else 'unknown'}:{symbol.start_line}\n"
        )
    
    for child in tree.get('children', []):
        lines.append(_format_hierarchy_tree(child, root_name, indent + 1))
    
    return "".join(lines)


async def _find_callers(
    symbol_id: int,
    limit: int = 50,
) -> List[TextContent]:
    """Find all symbols that call this one."""
    try:
        async with get_async_session() as session:
            # Get the symbol
            result = await session.execute(
                select(Symbol).where(Symbol.id == symbol_id)
            )
            symbol = result.scalar_one_or_none()
            
            if not symbol:
                return [TextContent(type="text", text=f"Symbol ID {symbol_id} not found")]
            
            # Find callers
            result = await session.execute(
                select(Symbol, File)
                .join(Relation, Relation.from_symbol_id == Symbol.id)
                .join(File, Symbol.file_id == File.id)
                .where(
                    Relation.to_symbol_id == symbol_id,
                    Relation.relation_type == RelationTypeEnum.CALLS
                )
                .limit(limit)
            )
            
            callers = result.all()
            
            if not callers:
                return [TextContent(type="text", text=f"No callers found for '{symbol.name}'")]
            
            # Format results
            formatted = [
                f"Found {len(callers)} callers of **{symbol.name}**:\n\n"
            ]
            
            for caller, file in callers:
                formatted.append(
                    f"- **{caller.name}** ({caller.kind.value})\n"
                    f"  File: {file.path}:{caller.start_line}\n\n"
                )
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_find_callers_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to find callers: {str(e)}",
            )
        ]


async def _find_callees(
    symbol_id: int,
    limit: int = 50,
) -> List[TextContent]:
    """Find all functions/methods that this symbol calls."""
    try:
        async with get_async_session() as session:
            # Get the symbol
            result = await session.execute(
                select(Symbol).where(Symbol.id == symbol_id)
            )
            symbol = result.scalar_one_or_none()
            
            if not symbol:
                return [TextContent(type="text", text=f"Symbol ID {symbol_id} not found")]
            
            # Find callees
            result = await session.execute(
                select(Symbol, File)
                .join(Relation, Relation.to_symbol_id == Symbol.id)
                .join(File, Symbol.file_id == File.id)
                .where(
                    Relation.from_symbol_id == symbol_id,
                    Relation.relation_type == RelationTypeEnum.CALLS
                )
                .limit(limit)
            )
            
            callees = result.all()
            
            if not callees:
                return [TextContent(type="text", text=f"'{symbol.name}' doesn't call any other symbols")]
            
            # Format results
            formatted = [
                f"**{symbol.name}** calls {len(callees)} functions/methods:\n\n"
            ]
            
            for callee, file in callees:
                formatted.append(
                    f"- **{callee.name}** ({callee.kind.value})\n"
                    f"  File: {file.path}:{callee.start_line}\n\n"
                )
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_find_callees_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to find callees: {str(e)}",
            )
        ]


async def _analyze_architecture(
    repository_id: int,
) -> List[TextContent]:
    """
    Analyze repository architecture and detect patterns.

    Args:
        repository_id: Repository ID

    Returns:
        Architecture analysis with detected patterns
    """
    try:
        async with get_async_session() as session:
            from src.extractors.pattern_detector import PatternDetector
            
            # Get repository info
            result = await session.execute(
                select(Repository).where(Repository.id == repository_id)
            )
            repo = result.scalar_one_or_none()
            
            if not repo:
                return [TextContent(type="text", text=f"Repository ID {repository_id} not found")]
            
            # Detect patterns
            detector = PatternDetector(session)
            patterns = await detector.detect_patterns(repository_id)
            
            if not patterns:
                return [TextContent(type="text", text=f"No patterns detected in repository")]
            
            # Group patterns by type
            by_type = {}
            for pattern in patterns:
                pattern_type = pattern.pattern_type
                if pattern_type not in by_type:
                    by_type[pattern_type] = []
                by_type[pattern_type].append(pattern)
            
            # Format results
            formatted = [
                f"# Architecture Analysis: {repo.name}\n\n",
                f"Detected {len(patterns)} patterns\n\n"
            ]
            
            # Design Patterns
            if 'design_pattern' in by_type:
                formatted.append(f"## Design Patterns ({len(by_type['design_pattern'])})\n\n")
                for pattern in by_type['design_pattern']:
                    formatted.append(
                        f"### {pattern.pattern_name}\n"
                        f"**Confidence**: {pattern.confidence:.0%}\n"
                        f"**Description**: {pattern.description}\n"
                        f"**Evidence**:\n"
                    )
                    for evidence in pattern.evidence:
                        formatted.append(f"- {evidence}\n")
                    formatted.append("\n")
            
            # Architectural Layers
            if 'architectural_layer' in by_type:
                formatted.append(f"## Architectural Layers ({len(by_type['architectural_layer'])})\n\n")
                for pattern in by_type['architectural_layer']:
                    formatted.append(
                        f"### {pattern.pattern_name}\n"
                        f"{pattern.description}\n\n"
                    )
            
            # Anti-Patterns
            if 'anti_pattern' in by_type:
                formatted.append(f"## ⚠️ Anti-Patterns ({len(by_type['anti_pattern'])})\n\n")
                for pattern in by_type['anti_pattern']:
                    formatted.append(
                        f"### {pattern.pattern_name}\n"
                        f"**Confidence**: {pattern.confidence:.0%}\n"
                        f"**Description**: {pattern.description}\n"
                        f"**Recommendations**:\n"
                    )
                    for evidence in pattern.evidence:
                        formatted.append(f"- {evidence}\n")
                    formatted.append("\n")
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_analyze_architecture_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to analyze architecture: {str(e)}",
            )
        ]


async def _search_by_path(
    repository_id: int,
    path_pattern: str,
    limit: int = 50,
) -> List[TextContent]:
    """
    Search for files by path pattern.

    Args:
        repository_id: Repository ID
        path_pattern: Path pattern with wildcards (e.g., '*/services/*.cs')
        limit: Maximum results

    Returns:
        List of matching files
    """
    try:
        async with get_async_session() as session:
            import re
            
            # Get repository
            result = await session.execute(
                select(Repository).where(Repository.id == repository_id)
            )
            repo = result.scalar_one_or_none()
            
            if not repo:
                return [TextContent(type="text", text=f"Repository ID {repository_id} not found")]
            
            # Get all files in repository
            result = await session.execute(
                select(File).where(File.repository_id == repository_id)
            )
            files = result.scalars().all()
            
            # Convert glob pattern to regex
            regex_pattern = path_pattern.replace('**', '<DOUBLE_STAR>')
            regex_pattern = regex_pattern.replace('*', '[^/]*')
            regex_pattern = regex_pattern.replace('<DOUBLE_STAR>', '.*')
            regex_pattern = f"^{regex_pattern}$"
            
            # Filter files by pattern
            matching_files = []
            for file in files:
                if re.match(regex_pattern, file.path, re.IGNORECASE):
                    matching_files.append(file)
                    if len(matching_files) >= limit:
                        break
            
            if not matching_files:
                return [TextContent(type="text", text=f"No files match pattern: '{path_pattern}'")]
            
            # Get symbol counts for matching files
            file_ids = [file.id for file in matching_files]
            symbol_counts_result = await session.execute(
                select(
                    Symbol.file_id,
                    func.count(Symbol.id).label('count')
                )
                .where(Symbol.file_id.in_(file_ids))
                .group_by(Symbol.file_id)
            )
            symbol_counts = {row.file_id: row.count for row in symbol_counts_result}
            
            # Format results
            formatted = [
                f"# Files matching '{path_pattern}'\n",
                f"Repository: **{repo.name}**\n",
                f"Found: {len(matching_files)} files\n\n"
            ]
            
            for file in matching_files:
                symbol_count = symbol_counts.get(file.id, 0)
                formatted.append(
                    f"## {file.path}\n"
                    f"- **Language**: {file.language.value}\n"
                    f"- **Lines**: {file.line_count}\n"
                    f"- **Symbols**: {symbol_count}\n"
                    f"- **Size**: {file.size_bytes} bytes\n\n"
                )
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_search_by_path_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to search by path: {str(e)}",
            )
        ]


async def _trace_request_flow(
    endpoint: str,
    repository_id: int,
) -> List[TextContent]:
    """
    Trace request flow through application layers, including cross-service calls.

    Args:
        endpoint: API endpoint (e.g., 'POST /api/users')
        repository_id: Repository ID

    Returns:
        Request flow trace
    """
    try:
        import re
        
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
            controller_method_result = await session.execute(
                select(Symbol)
                .where(
                    Symbol.file_id == matching_symbol.file_id,
                    Symbol.kind == SymbolKindEnum.METHOD,
                    Symbol.start_line == matching_symbol.start_line
                )
            )
            method_symbol = controller_method_result.scalars().first()
            
            # If not found by exact line, use the endpoint symbol itself
            if not method_symbol:
                method_symbol = matching_symbol
            
            # Trace calls from controller method
            call_chain = await _build_call_chain(session, method_symbol.id, depth=3)
            
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
                "## Flow:\n\n"
            ]
            
            # Format call chain
            formatted.append(_format_call_chain(call_chain, 0))
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_trace_request_flow_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to trace request flow: {str(e)}",
            )
        ]


async def _build_call_chain(session: AsyncSession, symbol_id: int, depth: int = 3, visited: Optional[Set[int]] = None) -> Dict:
    """
    Build call chain for request flow tracing, including cross-service links.
    """
    if visited is None:
        visited = set()
    
    if symbol_id in visited or depth <= 0:
        return {"symbol_id": symbol_id, "calls": []}
    
    visited.add(symbol_id)
    
    # Get symbol
    result = await session.execute(select(Symbol).where(Symbol.id == symbol_id))
    symbol = result.scalar_one_or_none()
    
    if not symbol:
        return {"symbol_id": symbol_id, "calls": []}
    
    node = {
        "symbol": {
            "id": symbol.id,
            "name": symbol.name,
            "kind": symbol.kind.value,
            "file": "", # Will be populated
            "line": symbol.start_line,
            "repo": ""
        },
        "calls": [],
        "events": [],
        "api_calls": []
    }

    # Get file info
    file_result = await session.execute(select(File, Repository).join(Repository).where(File.id == symbol.file_id))
    file_row = file_result.first()
    if file_row:
        node["symbol"]["file"] = file_row.File.path
        node["symbol"]["repo"] = file_row.Repository.name

    # 1. Internal Calls
    result = await session.execute(
        select(Symbol, File)
        .join(Relation, Relation.to_symbol_id == Symbol.id)
        .join(File, Symbol.file_id == File.id)
        .where(
            Relation.from_symbol_id == symbol_id,
            Relation.relation_type == RelationTypeEnum.CALLS
        )
    )
    
    for called_symbol, file in result.all():
        sub_chain = await _build_call_chain(session, called_symbol.id, depth - 1, visited)
        node["calls"].append(sub_chain)

    # 2. Cross-Service API Calls (Phase 3)
    # Find outgoing API calls from this symbol
    api_links = await session.execute(
        select(ApiEndpointLink, Symbol, File, Repository)
        .join(Symbol, ApiEndpointLink.target_symbol_id == Symbol.id)
        .join(File, Symbol.file_id == File.id)
        .join(Repository, File.repository_id == Repository.id)
        .where(ApiEndpointLink.source_symbol_id == symbol_id)
    )
    
    for link, target_symbol, target_file, target_repo in api_links.all():
        # Recurse into the target microservice
        # We treat this as a "call" but mark it as cross-service
        sub_chain = await _build_call_chain(session, target_symbol.id, depth - 1, visited)
        sub_chain["type"] = "cross_service"
        sub_chain["method"] = link.http_method
        sub_chain["url"] = link.url_pattern
        sub_chain["confidence"] = link.match_confidence
        node["api_calls"].append(sub_chain)

    # 3. Published Events (Phase 3)
    # Find events published by this symbol
    event_links = await session.execute(
        select(EventLink, Symbol, File, Repository)
        .join(Symbol, EventLink.subscriber_symbol_id == Symbol.id)
        .join(File, Symbol.file_id == File.id)
        .join(Repository, File.repository_id == Repository.id)
        .where(EventLink.publisher_symbol_id == symbol_id)
    )
    
    for link, sub_symbol, sub_file, sub_repo in event_links.all():
        # Recurse into the subscriber
        sub_chain = await _build_call_chain(session, sub_symbol.id, depth - 1, visited)
        sub_chain["type"] = "event_pub"
        sub_chain["event_type"] = link.event_type
        sub_chain["topic"] = link.topic
        sub_chain["confidence"] = link.match_confidence
        node["events"].append(sub_chain)
    
    return node


def _format_call_chain(chain: Dict, indent: int = 0) -> str:
    """Format call chain as indented tree."""
    formatted = []
    prefix = "  " * indent
    
    # 1. Internal Calls
    if "calls" in chain and chain["calls"]:
        for call in chain["calls"]:
            symbol = call.get("symbol", {})
            formatted.append(
                f"{prefix}→ **{symbol.get('name')}** ({symbol.get('kind')})\n"
                f"{prefix}  {symbol.get('file')}:{symbol.get('line')}\n"
            )
            formatted.append(_format_call_chain(call, indent + 1))

    # 2. Cross-Service API Calls
    if "api_calls" in chain and chain["api_calls"]:
        for call in chain["api_calls"]:
            symbol = call.get("symbol", {})
            formatted.append(
                f"{prefix}🌐 **HTTP {call.get('method')} {call.get('url')}**\n"
                f"{prefix}  ↳ **{symbol.get('name')}** in `{symbol.get('repo')}`\n"
                f"{prefix}  Confidence: {call.get('confidence')}%\n"
            )
            formatted.append(_format_call_chain(call, indent + 1))

    # 3. Published Events
    if "events" in chain and chain["events"]:
        for event in chain["events"]:
            symbol = event.get("symbol", {})
            formatted.append(
                f"{prefix}⚡ **Publishes {event.get('event_type')}**\n"
                f"{prefix}  ↳ Subscribed: **{symbol.get('name')}** in `{symbol.get('repo')}`\n"
                f"{prefix}  Topic: {event.get('topic')}\n"
            )
            formatted.append(_format_call_chain(event, indent + 1))
    
    return "".join(formatted)


async def _list_repositories(limit: int = 20) -> List[TextContent]:
    """
    List available repositories.

    Args:
        limit: Maximum number of repositories to return

    Returns:
        List of repositories with their status and statistics
    """
    try:
        async with get_async_session() as session:
            result = await session.execute(select(Repository).limit(limit))
            repos = result.scalars().all()

            repo_list = []
            for repo in repos:
                repo_list.append(
                    {
                        # Primary ID (ENHANCED)
                        "id": repo.id,
                        # Basic info
                        "name": repo.name,
                        "provider": repo.provider.value,
                        "path_with_namespace": repo.path_with_namespace,
                        # Access URLs (ENHANCED)
                        "url": repo.url,
                        "clone_url": repo.clone_url,
                        "default_branch": repo.default_branch,
                        # Status and stats
                        "status": repo.status.value,
                        "total_files": repo.total_files,
                        "total_symbols": repo.total_symbols,
                        "size_bytes": repo.size_bytes,
                        # Timestamps
                        "last_synced": repo.last_synced_at.isoformat()
                        if repo.last_synced_at
                        else None,
                        "last_commit_sha": repo.last_commit_sha,
                        "created_at": repo.created_at.isoformat() if repo.created_at else None,
                        # Provider-specific (ENHANCED)
                        "gitlab_project_id": repo.gitlab_project_id,
                        "azuredevops_project_name": repo.azuredevops_project_name,
                        "azuredevops_repo_id": repo.azuredevops_repo_id,
                    }
                )

            formatter = await _get_formatter()
            return [
                TextContent(
                    type="text",
                    text=formatter._format_repository_list(repo_list),
                )
            ]

    except Exception as e:
        logger.error("mcp_list_repositories_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to list repositories: {str(e)}",
            )
        ]


async def _get_project_map(
    repository_id: int, max_depth: int = 2
) -> List[TextContent]:
    """
    Get hierarchical project map with annotations.

    Args:
        repository_id: Repository ID to map
        max_depth: Maximum directory depth to traverse (default: 2)

    Returns:
        Markdown-formatted project map
    """
    # Validate required parameters
    if repository_id is None:
        return [
            TextContent(
                type="text",
                text="❌ Missing required parameter: repository_id\n\n"
                "💡 Use `list_repositories()` to find available repositories and their IDs."
            )
        ]
    
    start_time = time.time()

    try:
        from src.utils.project_mapper import ProjectMapper

        async with get_async_session() as session:
            mapper = ProjectMapper(session)
            project_map = await mapper.generate_project_map(
                repository_id=repository_id, max_depth=max_depth
            )

            duration = time.time() - start_time
            mcp_tool_duration.labels(tool=MCPToolEnum.GET_PROJECT_MAP.value).observe(
                duration
            )
            mcp_tool_calls_total.labels(
                tool=MCPToolEnum.GET_PROJECT_MAP.value, status="success"
            ).inc()

            logger.info(
                "mcp_get_project_map_success",
                repository_id=repository_id,
                max_depth=max_depth,
                duration=duration,
            )

            return [TextContent(type="text", text=project_map)]

    except Exception as e:
        duration = time.time() - start_time
        mcp_tool_calls_total.labels(
            tool=MCPToolEnum.GET_PROJECT_MAP.value, status="error"
        ).inc()
        logger.error(
            "mcp_get_project_map_failed",
            repository_id=repository_id,
            error=str(e),
            exc_info=True,
        )
        return [
            TextContent(
                type="text",
                text=f"Failed to generate project map: {str(e)}",
            )
        ]


async def _get_module_summary(
    repository_id: int,
    module_path: str,
    generate_if_missing: bool = True
) -> List[TextContent]:
    """
    Get AI-generated summary for a specific module.

    Args:
        repository_id: Repository ID
        module_path: Path to module (e.g., "src/api", "backend/auth")
        generate_if_missing: Generate summary if it doesn't exist (default: True)

    Returns:
        Module summary with purpose, key components, and entry points
    """
    # Validate required parameters
    if repository_id is None:
        return [
            TextContent(
                type="text",
                text="❌ Missing required parameter: repository_id\n\n"
                "💡 Use `list_repositories()` to find available repositories and their IDs."
            )
        ]
    
    if not module_path:
        return [
            TextContent(
                type="text",
                text="❌ Missing required parameter: module_path\n\n"
                "💡 Use `get_project_map(repository_id)` to see available module paths.\n"
                "Example: 'src/api', 'backend/auth', 'frontend/components'"
            )
        ]
    
    start_time = time.time()

    try:
        from src.utils.module_summary_generator import ModuleSummaryGenerator

        async with get_async_session() as session:
            generator = ModuleSummaryGenerator(session)
            summary = await generator.get_module_summary(
                repository_id=repository_id,
                module_path=module_path,
                generate_if_missing=generate_if_missing
            )

            if not summary:
                return [
                    TextContent(
                        type="text",
                        text=f"❌ Module summary not found for '{module_path}' in repository {repository_id}.\n\n"
                        f"The module may not exist or may not have been analyzed yet.\n\n"
                        f"💡 Tips:\n"
                        f"- Use `get_project_map(repository_id={repository_id})` to see available modules\n"
                        f"- Ensure the repository has been fully indexed\n"
                        f"- Check that the module path is correct (e.g., 'src/api', not 'src/api/')",
                    )
                ]

            # Format summary for display
            formatted = _format_module_summary(summary)

            duration = time.time() - start_time
            mcp_tool_duration.labels(tool=MCPToolEnum.GET_MODULE_SUMMARY.value).observe(
                duration
            )
            mcp_tool_calls_total.labels(
                tool=MCPToolEnum.GET_MODULE_SUMMARY.value, status="success"
            ).inc()

            logger.info(
                "mcp_get_module_summary_success",
                repository_id=repository_id,
                module_path=module_path,
                duration=duration,
            )

            return [TextContent(type="text", text=formatted)]

    except Exception as e:
        duration = time.time() - start_time
        mcp_tool_calls_total.labels(
            tool=MCPToolEnum.GET_MODULE_SUMMARY.value, status="error"
        ).inc()
        logger.error(
            "mcp_get_module_summary_failed",
            repository_id=repository_id,
            module_path=module_path,
            error=str(e),
            exc_info=True,
        )
        return [
            TextContent(
                type="text",
                text=f"Failed to get module summary: {str(e)}",
            )
        ]


async def _query_codebase_structure(
    query: str,
    repository_id: Optional[int] = None,
    limit: int = 50
) -> List[TextContent]:
    """
    Query codebase structure using natural language (Phase 4: Text-to-SQL).
    
    Translates natural language queries into SQL queries against the codebase schema,
    enabling complex architectural queries that semantic search cannot handle.
    
    Args:
        query: Natural language query (e.g., "Find all public methods in controllers")
        repository_id: Optional repository filter
        limit: Maximum results (default: 50)
        
    Returns:
        Query results with symbols matching the criteria
        
    Examples:
        - "Find all controllers"
        - "List public methods without documentation"
        - "Show methods with complexity > 10"
        - "Find classes that inherit from BaseController"
    """
    # Validate required parameters
    if not query:
        return [
            TextContent(
                type="text",
                text="❌ Missing required parameter: query\n\n"
                "💡 Examples of valid queries:\n"
                "- Find all controllers\n"
                "- List public methods\n"
                "- Show complex methods\n"
                "- Find undocumented symbols\n"
                "- Get Python/TypeScript/CSharp classes\n"
                "- Find unused symbols\n"
                "- Show largest classes"
            )
        ]
    
    start_time = time.time()
    
    try:
        async with get_async_session() as session:
            translator = TextToSQLTranslator(session)
            
            # Translate natural language to SQL
            sql_query = await translator.translate(
                natural_language_query=query,
                repository_id=repository_id,
                limit=limit
            )
            
            if not sql_query:
                return [
                    TextContent(
                        type="text",
                        text=f"❌ Could not translate query: '{query}'\n\n"
                        f"💡 Try one of these supported patterns:\n"
                        f"- Find all controllers\n"
                        f"- List public methods\n"
                        f"- Show complex methods\n"
                        f"- Find undocumented symbols\n"
                        f"- Get Python/TypeScript/CSharp classes\n"
                        f"- Find unused symbols\n"
                        f"- Show largest classes\n"
                        f"- List inheritance hierarchies"
                    )
                ]
            
            # Execute query
            result = await translator.execute(sql_query)
            
            # Format results
            formatted_text = translator.format_results_markdown(result)
            
            duration = time.time() - start_time
            mcp_tool_duration.labels(tool="query_codebase_structure").observe(duration)
            mcp_tool_calls_total.labels(tool="query_codebase_structure", status="success").inc()
            
            logger.info(
                "mcp_query_codebase_structure_complete",
                query=query,
                row_count=result.row_count,
                execution_time_ms=result.execution_time_ms,
                duration=duration
            )
            
            return [TextContent(type="text", text=formatted_text)]
            
    except ValueError as e:
        # Safety validation error
        logger.warning("mcp_query_codebase_structure_validation_failed", error=str(e), query=query)
        mcp_tool_calls_total.labels(tool="query_codebase_structure", status="error").inc()
        return [
            TextContent(
                type="text",
                text=f"❌ Query validation failed: {str(e)}\n\n"
                f"Queries must be safe, read-only operations."
            )
        ]
    except Exception as e:
        logger.error(
            "mcp_query_codebase_structure_failed",
            query=query,
            error=str(e),
            exc_info=True
        )
        mcp_tool_calls_total.labels(tool="query_codebase_structure", status="error").inc()
        return [
            TextContent(
                type="text",
                text=f"Failed to query codebase structure: {str(e)}",
            )
        ]


def _format_module_summary(summary) -> str:
    """Format module summary for display."""
    lines = []

    # Header
    package_indicator = " 📦 Package" if summary.is_package else ""
    lines.append(f"# 🎯 Module Summary: **{summary.module_name}**{package_indicator}\n")
    lines.append(f"**Path**: `{summary.module_path}`")
    lines.append(f"**Type**: {summary.module_type.replace('_', ' ').title()}")
    lines.append("")

    # Summary
    lines.append("## 📝 Overview\n")
    lines.append(summary.summary)
    lines.append("")

    # Purpose
    if summary.purpose:
        lines.append("## 🎯 Purpose\n")
        lines.append(summary.purpose)
        lines.append("")

    # Statistics
    lines.append("## 📊 Statistics\n")
    lines.append(f"- **Files**: {summary.file_count}")
    lines.append(f"- **Symbols**: {summary.symbol_count}")
    lines.append(f"- **Lines of Code**: {summary.line_count:,}")

    if summary.complexity_score:
        complexity_emoji = "🟢" if summary.complexity_score <= 3 else "🟡" if summary.complexity_score <= 7 else "🔴"
        lines.append(f"- **Complexity**: {complexity_emoji} {summary.complexity_score}/10")
    lines.append("")

    # Entry Points
    if summary.entry_points:
        lines.append("## 🚪 Entry Points\n")
        for ep in summary.entry_points:
            ep_type = ep.get("type", "unknown").replace("_", " ").title()
            lines.append(f"- `{ep['file']}` ({ep_type})")
        lines.append("")

    # Key Components
    if summary.key_components:
        lines.append("## 🔑 Key Components\n")
        for comp in summary.key_components[:10]:  # Limit to top 10
            comp_type = comp.get("type", "component").upper()
            lines.append(f"### {comp_type}: `{comp['name']}`")
            if comp.get("description"):
                lines.append(f"{comp['description']}\n")
        lines.append("")

    # Dependencies
    if summary.dependencies:
        deps = summary.dependencies
        if deps.get("internal") or deps.get("external"):
            lines.append("## 🔗 Dependencies\n")

            if deps.get("internal"):
                lines.append("**Internal Modules**:")
                for dep in deps["internal"][:5]:
                    lines.append(f"- `{dep}`")
                lines.append("")

            if deps.get("external"):
                lines.append("**External Packages**:")
                for dep in deps["external"][:10]:
                    lines.append(f"- `{dep}`")
                lines.append("")

    # Metadata
    lines.append("---\n")
    lines.append("## ℹ️ Metadata\n")
    lines.append(f"- **Generated By**: {summary.generated_by or 'Unknown'}")
    lines.append(f"- **Generated**: {summary.generated_at.strftime('%Y-%m-%d %H:%M:%S') if summary.generated_at else 'Unknown'}")
    lines.append(f"- **Last Updated**: {summary.last_updated.strftime('%Y-%m-%d %H:%M:%S') if summary.last_updated else 'Unknown'}")
    lines.append(f"- **Version**: {summary.version}")
    lines.append("")

    # Tips
    lines.append("## 💡 Next Steps\n")
    lines.append(f"- Use `get_file_tree(repository_id, path=\"{summary.module_path}\")` for detailed file structure")
    lines.append(f"- Use `search_by_path(repository_id, path_pattern=\"{summary.module_path}/**\")` to find specific files")
    lines.append(f"- Use `search_code(query=\"...\", repository_id)` to find symbols in this module")

    return "\n".join(lines)
