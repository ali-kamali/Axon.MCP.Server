from typing import List, Optional, Dict, Any, Set
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcp.types import TextContent

from src.config.enums import RelationTypeEnum
from src.database.models import File, Symbol, Relation
from src.database.session import get_async_session
from src.utils.logging_config import get_logger
from src.mcp_server.formatters.hierarchy import format_hierarchy_tree

logger = get_logger(__name__)

async def get_call_hierarchy(
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
            formatted.append(format_hierarchy_tree(hierarchy, symbol.name, 0))
            
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
        # Only add if we got a valid tree (child_tree already has symbol, file, children)
        if child_tree:
            children.append(child_tree)
    
    return {
        'symbol': symbol,
        'file': file,
        'children': children
    }


async def find_callers(
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


async def find_callees(
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
