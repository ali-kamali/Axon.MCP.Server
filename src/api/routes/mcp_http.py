"""MCP HTTP transport endpoint for remote connections."""

import json
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import Response, StreamingResponse

from src.config.settings import get_settings
from src.utils.logging_config import get_logger
from src.api.auth import get_current_user_mcp

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(dependencies=[Depends(get_current_user_mcp)])


async def _handle_mcp_request(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle MCP JSON-RPC request."""
    try:
        method = request_data.get("method")
        params = request_data.get("params") or {}
        request_id = request_data.get("id")

        if method == "initialize":
            # Return server capabilities
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {
                        "tools": {},
                    },
                    "serverInfo": {
                        "name": "axon-mcp-server",
                        "version": settings.app_version,
                    },
                },
            }
        elif method == "tools/list":
            # List available tools - call the decorated function directly
            from src.mcp_server.server import list_tools
            tools = await list_tools()
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.inputSchema,
                        }
                        for tool in tools
                    ]
                },
            }
        elif method == "tools/call":
            # Call a tool
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            if not tool_name:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32602,
                        "message": "Invalid params",
                        "data": "Tool name is required",
                    },
                }
            
            # Call the tool handler - call the decorated function directly
            from src.mcp_server.server import call_tool
            result = await call_tool(tool_name, arguments)
            
            # Format response
            content = []
            for item in result:
                content.append({"type": item.type, "text": item.text})
            
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": content,
                    "isError": False,
                },
            }
        elif method == "resources/list":
            # List available resources
            from src.mcp_server.server import _list_mcp_resources
            resources = await _list_mcp_resources()
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "resources": resources
                },
            }
        elif method == "resources/read":
            # Read a specific resource
            resource_uri = params.get("uri")
            
            if not resource_uri:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32602,
                        "message": "Invalid params",
                        "data": "Resource URI is required",
                    },
                }
            
            from src.mcp_server.server import _read_mcp_resource
            result = await _read_mcp_resource(resource_uri)
            
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "contents": [result]
                },
            }
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": "Method not found",
                    "data": f"Unknown method: {method}",
                },
            }
    except Exception as e:
        logger.error("mcp_http_request_failed", error=str(e), exc_info=True)
        return {
            "jsonrpc": "2.0",
            "id": request_data.get("id"),
            "error": {
                "code": -32603,
                "message": "Internal error",
                "data": "An internal error occurred while processing the request",
            },
        }


@router.post("/mcp")
async def mcp_http_endpoint(request: Request) -> Response:
    """
    MCP HTTP transport endpoint.
    
    Handles JSON-RPC requests over HTTP for remote MCP client connections.
    """
    try:
        # Parse JSON-RPC request
        body = await request.body()
        request_data = json.loads(body.decode("utf-8"))
        
        logger.info("mcp_http_request", method=request_data.get("method"))
        
        # Handle the request
        response_data = await _handle_mcp_request(request_data)
        
        return Response(
            content=json.dumps(response_data),
            media_type="application/json",
        )
    except json.JSONDecodeError as e:
        logger.error("mcp_http_invalid_json", error=str(e))
        error_response = {
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": -32700,
                "message": "Parse error",
                "data": "Invalid JSON in request body",
            },
        }
        return Response(
            content=json.dumps(error_response),
            media_type="application/json",
            status_code=400,
        )
    except Exception as e:
        logger.error("mcp_http_error", error=str(e), exc_info=True)
        error_response = {
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": -32603,
                "message": "Internal error",
                "data": "An unexpected error occurred",
            },
        }
        return Response(
            content=json.dumps(error_response),
            media_type="application/json",
            status_code=500,
        )


@router.get("/mcp/sse")
async def mcp_sse_endpoint(request: Request) -> StreamingResponse:
    """
    MCP Server-Sent Events (SSE) endpoint for streaming responses.
    
    This endpoint supports streaming responses for long-running operations.
    """
    # For now, we'll use regular HTTP POST for simplicity
    # SSE can be added later if needed for streaming
    raise HTTPException(
        status_code=501,
        detail="SSE streaming not yet implemented. Use POST endpoint instead.",
    )

