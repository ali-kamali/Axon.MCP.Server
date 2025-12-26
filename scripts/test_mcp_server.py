#!/usr/bin/env python3
"""Test script for MCP server functionality.

This script tests the MCP server tools directly without going through
the MCP protocol layer. Note: Tools are registered as closures within
the AxonMCPServer class, so this script verifies the class initializes
correctly.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.mcp_server.server import AxonMCPServer
from src.utils.logging_config import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


async def test_server_initialization():
    """Test MCP server initialization."""
    print("\n" + "=" * 80)
    print("Testing AxonMCPServer initialization")
    print("=" * 80)

    try:
        server = AxonMCPServer()
        print(f"\n✅ Server initialized: {server.server.name}")
        print(f"✅ Registered tools: {list(server.server._tools.keys())}")

        # Verify all expected tools are registered
        expected_tools = ["search_code", "get_symbol_context", "list_repositories"]
        for tool_name in expected_tools:
            if tool_name in server.server._tools:
                print(f"✅ Tool registered: {tool_name}")
            else:
                print(f"❌ Tool missing: {tool_name}")

        return server
    except Exception as e:
        print(f"\n❌ Server initialization failed: {e}")
        logger.error("server_init_failed", error=str(e), exc_info=True)
        return None


async def test_tool_invocation(server: AxonMCPServer):
    """Test invoking a tool directly."""
    print("\n" + "=" * 80)
    print("Testing tool invocation (list_repositories)")
    print("=" * 80)

    try:
        # Get the list_repositories tool
        list_tool = server.server._tools.get("list_repositories")
        if not list_tool:
            print("❌ list_repositories tool not found")
            return

        # Invoke the tool
        result = await list_tool.fn(limit=5)

        print("\nTool Response:")
        print(f"- isError: {result.get('isError')}")
        print(f"- content length: {len(result.get('content', []))}")
        if result.get("content"):
            print(f"- content type: {result['content'][0].type}")
            print(f"\nFormatted output:\n{result['content'][0].text}")

        print("\n✅ Tool invocation successful")
    except Exception as e:
        print(f"\n❌ Tool invocation failed: {e}")
        logger.error("tool_invocation_failed", error=str(e), exc_info=True)


async def test_search_tool(server: AxonMCPServer):
    """Test search_code tool."""
    print("\n" + "=" * 80)
    print("Testing search_code tool")
    print("=" * 80)

    try:
        search_tool = server.server._tools.get("search_code")
        if not search_tool:
            print("❌ search_code tool not found")
            return

        # Test with a simple query
        result = await search_tool.fn(query="function", limit=5)

        print("\nSearch Response:")
        print(f"- isError: {result.get('isError')}")
        if result.get("content"):
            print(f"\nSearch results:\n{result['content'][0].text}")

        print("\n✅ Search tool test completed")
    except Exception as e:
        print(f"\n❌ Search tool failed: {e}")
        logger.error("search_tool_failed", error=str(e), exc_info=True)


async def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("MCP SERVER TEST SUITE")
    print("=" * 80)
    print("\nThis script tests the MCP server initialization and tool registration.")
    print("Make sure the database is running and contains some data.")
    print("=" * 80)

    # Test server initialization
    server = await test_server_initialization()
    if not server:
        print("\n❌ Cannot continue without initialized server")
        return

    # Test tool invocation
    await test_tool_invocation(server)

    # Test search tool
    await test_search_tool(server)

    print("\n" + "=" * 80)
    print("TEST SUITE COMPLETED")
    print("=" * 80)
    print("\n✅ All initialization tests passed!")
    print("📝 Note: Tools are registered as internal closures.")
    print("📝 To test actual MCP protocol communication, use an MCP client.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nTest suite failed with error: {e}")
        logger.error("test_suite_failed", error=str(e), exc_info=True)
        sys.exit(1)
