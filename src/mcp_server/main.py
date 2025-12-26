"""MCP Server main entry point for direct execution.

This module provides a direct entry point for the MCP server.
For module execution, use: python -m src.mcp_server
"""

import asyncio
import uvicorn

from src.config.settings import settings
from src.mcp_server.server import AxonMCPServer
from src.utils.logging_config import configure_logging, get_logger

# Configure logging
configure_logging()
logger = get_logger(__name__)


def main():
    """Main entry point for MCP server."""
    logger.info("mcp_server_starting", transport=settings.mcp_transport)

    try:
        if settings.mcp_transport == "http":
            # Run HTTP transport via FastAPI
            logger.info("starting_mcp_http_server", 
                       host=settings.mcp_http_host, 
                       port=settings.mcp_http_port)
            
            # Import the FastAPI app that includes MCP HTTP routes
            from src.api.main import app
            
            uvicorn.run(
                app,
                host=settings.mcp_http_host,
                port=settings.mcp_http_port,
                log_level=settings.log_level.lower(),
                access_log=True
            )
        else:
            # Run stdio transport (default)
            server = AxonMCPServer()
            asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("mcp_server_stopped_by_user")
    except Exception as e:
        logger.error("mcp_server_failed", error=str(e), exc_info=True)
        raise


if __name__ == "__main__":
    main()
