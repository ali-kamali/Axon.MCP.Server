"""MCP server for ChatGPT integration."""

from typing import Any, Dict, List

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from src.utils.logging_config import get_logger
from src.mcp_server.tools import TOOLS, route_tool_call
from src.mcp_server.resources.handlers import list_mcp_resources, read_mcp_resource

logger = get_logger(__name__)

# Create module-level server instance
mcp = Server("axon-mcp-server")


class AxonMCPServer:
    """MCP server for ChatGPT integration."""

    def __init__(self):
        """Initialize MCP server."""
        self.server = mcp
        self._register_tools()
        self._register_resources()
        logger.info("mcp_server_initialized")

    def _register_tools(self):
        """Register all MCP tools."""
        # Tools are registered at module level using decorators
        # This method is kept for initialization tracking
        pass

    def _register_resources(self):
        """Register MCP resources."""
        # Resources are registered at module level using decorators
        # This method is kept for initialization tracking
        pass

    async def start(self):
        """Start MCP server with stdio transport."""
        logger.info("mcp_server_starting")
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


# Register tool list handler
@mcp.list_tools()
async def list_tools() -> List[Tool]:
    """List available tools."""
    return TOOLS


# Register tool call handler
@mcp.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool calls by routing to appropriate handlers."""
    return await route_tool_call(name, arguments)


# Register resource handlers
@mcp.list_resources()
async def list_resources():
    """List available resources."""
    return await list_mcp_resources()


@mcp.read_resource()
async def read_resource(uri: str):
    """Read a specific resource."""
    return await read_mcp_resource(uri)


# Main entry point
async def main():
    """Main entry point for MCP server."""
    server = AxonMCPServer()
    await server.start()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
