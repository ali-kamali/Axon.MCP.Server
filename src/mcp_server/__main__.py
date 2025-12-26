"""MCP Server main entry point for running as a module.

Usage:
    python -m src.mcp_server
"""

import asyncio

from src.mcp_server.server import AxonMCPServer
from src.utils.logging_config import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


def main():
    """Main entry point for MCP server."""
    logger.info("mcp_server_starting")

    try:
        server = AxonMCPServer()
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("mcp_server_stopped_by_user")
    except Exception as e:
        logger.error("mcp_server_failed", error=str(e), exc_info=True)
        raise


if __name__ == "__main__":
    main()
