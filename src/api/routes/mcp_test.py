"""MCP Server testing endpoints for UI integration."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db_session
from src.mcp_server.tools.repository import list_repositories
from src.mcp_server.tools.search import search_code
from src.mcp_server.tools.symbols import get_symbol_context
from src.utils.logging_config import get_logger
from src.api.auth import get_current_user

logger = get_logger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])


class MCPSearchCodeRequest(BaseModel):
    """Request model for search_code MCP tool."""

    query: str = Field(..., min_length=1, max_length=200)
    limit: int = Field(10, ge=1, le=50)
    repository_name: Optional[str] = None
    language: Optional[str] = None
    symbol_kind: Optional[str] = None


class MCPGetSymbolContextRequest(BaseModel):
    """Request model for get_symbol_context MCP tool."""

    symbol_id: int = Field(..., gt=0)
    include_relationships: bool = True


class MCPListRepositoriesRequest(BaseModel):
    """Request model for list_repositories MCP tool."""

    limit: int = Field(20, ge=1, le=100)


class MCPToolResponse(BaseModel):
    """Response model for MCP tool calls."""

    content: list[Dict[str, Any]]
    isError: bool


@router.post("/mcp/tools/search_code", response_model=MCPToolResponse)
async def test_search_code(
    request: MCPSearchCodeRequest,
    session: AsyncSession = Depends(get_db_session),
) -> MCPToolResponse:
    """
    Test the search_code MCP tool.
    
    This endpoint allows the UI to test the MCP server's search_code tool
    directly, simulating how Claude or ChatGPT would interact with it.
    """
    try:
        logger.info("mcp_test_search_code", query=request.query)
        
        # Call the MCP tool function directly
        result = await search_code(
            query=request.query,
            limit=request.limit,
            repository_name=request.repository_name,
            language=request.language,
            symbol_kind=request.symbol_kind,
        )
        
        # Convert TextContent list to response format
        return MCPToolResponse(
            content=[{"type": item.type, "text": item.text} for item in result],
            isError=False,
        )
    
    except Exception as e:
        logger.error("mcp_test_search_code_failed", error=str(e), exc_info=True)
        return MCPToolResponse(
            content=[{"type": "text", "text": f"Error: {str(e)}"}],
            isError=True,
        )


@router.post("/mcp/tools/get_symbol_context", response_model=MCPToolResponse)
async def test_get_symbol_context(
    request: MCPGetSymbolContextRequest,
    session: AsyncSession = Depends(get_db_session),
) -> MCPToolResponse:
    """
    Test the get_symbol_context MCP tool.
    
    This endpoint allows the UI to test the MCP server's get_symbol_context tool
    directly, simulating how Claude or ChatGPT would interact with it.
    """
    try:
        logger.info("mcp_test_get_symbol_context", symbol_id=request.symbol_id)
        
        # Call the MCP tool function directly
        result = await get_symbol_context(
            symbol_id=request.symbol_id,
            include_relationships=request.include_relationships,
        )
        
        # Convert TextContent list to response format
        return MCPToolResponse(
            content=[{"type": item.type, "text": item.text} for item in result],
            isError=False,
        )
    
    except Exception as e:
        logger.error("mcp_test_get_symbol_context_failed", error=str(e), exc_info=True)
        return MCPToolResponse(
            content=[{"type": "text", "text": f"Error: {str(e)}"}],
            isError=True,
        )


@router.post("/mcp/tools/list_repositories", response_model=MCPToolResponse)
async def test_list_repositories(
    request: MCPListRepositoriesRequest,
    session: AsyncSession = Depends(get_db_session),
) -> MCPToolResponse:
    """
    Test the list_repositories MCP tool.
    
    This endpoint allows the UI to test the MCP server's list_repositories tool
    directly, simulating how Claude or ChatGPT would interact with it.
    """
    try:
        logger.info("mcp_test_list_repositories", limit=request.limit)
        
        # Call the MCP tool function directly
        result = await list_repositories(limit=request.limit)
        
        # Convert TextContent list to response format
        return MCPToolResponse(
            content=[{"type": item.type, "text": item.text} for item in result],
            isError=False,
        )
    
    except Exception as e:
        logger.error("mcp_test_list_repositories_failed", error=str(e), exc_info=True)
        return MCPToolResponse(
            content=[{"type": "text", "text": f"Error: {str(e)}"}],
            isError=True,
        )


@router.post("/mcp/tools/call", response_model=MCPToolResponse)
async def call_generic_tool(
    request: Dict[str, Any],
    session: AsyncSession = Depends(get_db_session),
) -> MCPToolResponse:
    """
    Call any MCP tool dynamically.
    
    This generic endpoint allows the UI to test any available MCP tool
    by passing the tool name and arguments.
    """
    try:
        tool_name = request.get("name")
        arguments = request.get("arguments", {})
        
        if not tool_name:
            raise HTTPException(status_code=400, detail="Tool name is required")
            
        logger.info("mcp_test_generic_call", tool=tool_name)
        
        # Import here to avoid circular imports if any
        from src.mcp_server.server import call_tool
        
        # Call the MCP tool function directly
        # call_tool is decorated, but we can call the underlying function if we access it correctly
        # Or since it's a FastMCP/mcp server object, we might need to invoke it differently.
        # However, looking at server.py, call_tool is a standalone async function decorated with @mcp.call_tool()
        # In python, decorators wrap the function, but usually the original function is still callable 
        # if the library doesn't replace it entirely with a non-callable object.
        # The mcp library likely registers it but keeps it callable.
        
        result = await call_tool(tool_name, arguments)
        
        # Convert TextContent list to response format
        return MCPToolResponse(
            content=[{"type": item.type, "text": item.text} for item in result],
            isError=False,
        )
    
    except Exception as e:
        logger.error("mcp_test_generic_call_failed", tool=request.get("name"), error=str(e), exc_info=True)
        return MCPToolResponse(
            content=[{"type": "text", "text": f"Error: {str(e)}"}],
            isError=True,
        )
