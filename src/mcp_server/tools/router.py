"""Tool router for MCP server."""

from typing import Any, Dict, List

from mcp.types import TextContent

from src.config.enums import MCPToolEnum
from src.utils.logging_config import get_logger

# Import all tool implementations
from src.mcp_server.tools.search import (
    search_code,
    search_documentation,
    search_configuration,
    search_by_path,
)
from src.mcp_server.tools.symbols import (
    get_symbol_context,
    find_usages,
    find_implementations,
    find_references,
)
from src.mcp_server.tools.repository import (
    list_repositories,
    get_file_tree,
    get_file_content,
    list_symbols_in_file,
    list_dependencies,
)
from src.mcp_server.tools.navigation import (
    get_call_hierarchy,
    find_callers,
    find_callees,
)
from src.mcp_server.tools.architecture import (
    analyze_architecture,
    trace_request_flow,
    find_api_endpoints,
)
from src.mcp_server.tools.exploration import (
    get_project_map,
    get_module_summary,
    query_codebase_structure,
)
from src.mcp_server.tools.service_tools import (
    list_services,
    get_service_details,
    get_service_documentation,
)
from src.mcp_server.tools.ef_tools import (
    list_ef_entities,
    get_db_entity_mapping,
)
from src.mcp_server.tools.system_map import get_system_map

logger = get_logger(__name__)

# Tool routing map
TOOL_HANDLERS = {
    MCPToolEnum.SEARCH_CODE.value: search_code,
    MCPToolEnum.GET_SYMBOL_CONTEXT.value: get_symbol_context,
    MCPToolEnum.LIST_REPOSITORIES.value: list_repositories,
    MCPToolEnum.SEARCH_DOCUMENTATION.value: search_documentation,
    MCPToolEnum.SEARCH_CONFIGURATION.value: search_configuration,
    MCPToolEnum.LIST_DEPENDENCIES.value: list_dependencies,
    MCPToolEnum.GET_FILE_CONTENT.value: get_file_content,
    MCPToolEnum.FIND_USAGES.value: find_usages,
    MCPToolEnum.FIND_IMPLEMENTATIONS.value: find_implementations,
    MCPToolEnum.FIND_REFERENCES.value: find_references,
    MCPToolEnum.GET_FILE_TREE.value: get_file_tree,
    MCPToolEnum.LIST_SYMBOLS_IN_FILE.value: list_symbols_in_file,
    MCPToolEnum.FIND_API_ENDPOINTS.value: find_api_endpoints,
    MCPToolEnum.GET_CALL_HIERARCHY.value: get_call_hierarchy,
    MCPToolEnum.FIND_CALLERS.value: find_callers,
    MCPToolEnum.FIND_CALLEES.value: find_callees,
    MCPToolEnum.ANALYZE_ARCHITECTURE.value: analyze_architecture,
    MCPToolEnum.SEARCH_BY_PATH.value: search_by_path,
    MCPToolEnum.TRACE_REQUEST_FLOW.value: trace_request_flow,
    MCPToolEnum.GET_PROJECT_MAP.value: get_project_map,
    MCPToolEnum.GET_MODULE_SUMMARY.value: get_module_summary,
    MCPToolEnum.QUERY_CODEBASE_STRUCTURE.value: query_codebase_structure,
    MCPToolEnum.LIST_SERVICES.value: list_services,
    MCPToolEnum.GET_SERVICE_DETAILS.value: get_service_details,
    MCPToolEnum.GET_SERVICE_DOCUMENTATION.value: get_service_documentation,
    MCPToolEnum.LIST_EF_ENTITIES.value: list_ef_entities,
    MCPToolEnum.GET_DB_ENTITY_MAPPING.value: get_db_entity_mapping,
    MCPToolEnum.GET_SYSTEM_MAP.value: get_system_map,
}


async def route_tool_call(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """
    Route tool calls to their respective handlers.
    
    Args:
        name: Tool name
        arguments: Tool arguments
        
    Returns:
        Tool execution result
    """
    handler = TOOL_HANDLERS.get(name)
    
    if not handler:
        logger.warning("unknown_tool_called", tool_name=name)
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    
    try:
        # Call the handler with unpacked arguments
        return await handler(**arguments)
    except TypeError as e:
        # Handle argument mismatch
        logger.error("tool_argument_error", tool_name=name, error=str(e), exc_info=True)
        return [TextContent(type="text", text=f"Invalid arguments for tool {name}: {str(e)}")]
    except Exception as e:
        # Handle any other errors
        logger.error("tool_execution_error", tool_name=name, error=str(e), exc_info=True)
        return [TextContent(type="text", text=f"Tool execution failed: {str(e)}")]
