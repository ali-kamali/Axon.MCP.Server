import time
from typing import List, Optional, Dict
from sqlalchemy import select, and_

from mcp.types import TextContent

from src.config.enums import RelationTypeEnum, SymbolKindEnum
from src.database.models import File, Repository, Symbol, Chunk, Relation
from src.database.session import get_async_session, get_readonly_session
from src.utils.logging_config import get_logger
from src.utils.metrics import mcp_tool_calls_total, mcp_tool_duration
from src.utils.call_graph_traversal import CallGraphTraverser, TraversalConfig, TraversalDirection
from src.services.link_service import get_connected_endpoints_for_symbol
from src.mcp_server.formatters.symbols import format_symbol_context

logger = get_logger(__name__)

async def get_symbol_context(
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
                mcp_tool_duration.labels(tool_name="get_symbol_context").observe(duration)
                mcp_tool_calls_total.labels(tool_name="get_symbol_context", status="success").inc()
                
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

                duration = time.time() - start_time
                mcp_tool_duration.labels(tool_name="get_symbol_context").observe(duration)
                mcp_tool_calls_total.labels(tool_name="get_symbol_context", status="success").inc()
                
                return [
                    TextContent(
                        type="text",
                        text=format_symbol_context(context),
                    )
                ]

    except Exception as e:
        logger.error("mcp_get_symbol_context_failed", error=str(e), exc_info=True)
        mcp_tool_calls_total.labels(tool_name="get_symbol_context", status="error").inc()
        return [
            TextContent(
                type="text",
                text=f"Failed to get symbol context: {str(e)}",
            )
        ]


async def find_usages(
    symbol_id: int,
    limit: int = 50,
    relationship_types: Optional[List[str]] = None,
) -> List[TextContent]:
    """
    Find all places where a symbol is used.

    Args:
        symbol_id: Symbol ID to find usages for
        limit: Maximum results
        relationship_types: Optional filter by relationship types (e.g., ['CALLS', 'USES'])

    Returns:
        List of usages
    """
    try:
        if symbol_id <= 0:
            return [TextContent(type="text", text="Invalid symbol_id: must be positive")]
        if limit < 1 or limit > 1000:
            limit = min(max(1, limit), 1000)
            
        async with get_async_session() as session:
            # Get the symbol
            result = await session.execute(
                select(Symbol).where(Symbol.id == symbol_id)
            )
            symbol = result.scalar_one_or_none()
            
            if not symbol:
                return [TextContent(type="text", text=f"Symbol ID {symbol_id} not found")]
            
            # Build query
            query = (
                select(Relation, Symbol, File)
                .join(Symbol, Relation.from_symbol_id == Symbol.id)
                .join(File, Symbol.file_id == File.id)
                .where(Relation.to_symbol_id == symbol_id)
            )

            # Apply relationship type filter
            if relationship_types:
                valid_enums = []
                for rt in relationship_types:
                    try:
                        valid_enums.append(RelationTypeEnum[rt])
                    except KeyError:
                        logger.warning(f"Invalid relationship type in filter: {rt}")
                
                if valid_enums:
                     query = query.where(Relation.relation_type.in_(valid_enums))

            query = query.limit(limit)

            # Find usages
            result = await session.execute(query)
            usages = result.all()
            
            if not usages:
                # Task 11: Contextual Suggestions
                suggestions = []
                
                # Check for Controller
                # Check attributes dict for 'ApiController' or ensure safe access
                is_controller = symbol.name.endswith("Controller")
                if not is_controller and symbol.attributes and isinstance(symbol.attributes, list):
                     # Attributes is list of dicts [{'name': 'ApiController', ...}]
                     is_controller = any(attr.get('name') == 'ApiController' for attr in symbol.attributes)
                
                if symbol.kind == SymbolKindEnum.CLASS and is_controller:
                    suggestions.append(f"💡 This looks like an API Controller. Try `find_api_endpoints` to see exposed routes.")
                
                # Check for Interface
                if symbol.kind == SymbolKindEnum.INTERFACE:
                    suggestions.append(f"💡 For interfaces, you might want `find_implementations(interface_id={symbol_id})`.")
                
                # Check for Repository/Service patterns
                if symbol.name.endswith("Repository") or symbol.name.endswith("Service"):
                    suggestions.append(f"💡 If looking for dependency injection usage, check `get_symbol_context` for DI registrations.")

                suggestion_text = "\n".join(suggestions)
                if suggestion_text:
                    suggestion_text = "\n\n" + suggestion_text

                return [TextContent(
                    type="text", 
                    text=f"No usages found for '{symbol.name}'.{suggestion_text}"
                )]
            
            # Group by relationship type
            by_type = {}
            for relation, using_symbol, file in usages:
                rel_type = relation.relation_type.value
                if rel_type not in by_type:
                    by_type[rel_type] = []
                by_type[rel_type].append((using_symbol, file))
            
            # Format results
            formatted = [
                f"Found {len(usages)} usages of **{symbol.name}** ({symbol.kind.value}):\n\n"
            ]
            
            for rel_type, items in by_type.items():
                formatted.append(f"### {rel_type.upper()} ({len(items)})\n\n")
                for using_symbol, file in items:
                    formatted.append(
                        f"- **{using_symbol.name}** ({using_symbol.kind.value})\n"
                        f"  File: {file.path}\n"
                        f"  Line: {using_symbol.start_line}\n\n"
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


async def find_implementations(
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
        async with get_readonly_session() as session:
            # Get the interface
            result = await session.execute(
                select(Symbol).where(Symbol.id == interface_id)
            )
            interface = result.scalar_one_or_none()
            
            if not interface:
                return [TextContent(type="text", text=f"Symbol ID {interface_id} not found")]
            
            # Validate it's actually an interface
            if interface.kind != SymbolKindEnum.INTERFACE:
                return [TextContent(
                    type="text",
                    text=(
                        f"❌ Symbol '{interface.name}' (ID: {interface_id}) is a **{interface.kind.value}**, not an INTERFACE.\n\n"
                        f"⚠️ The `find_implementations` tool ONLY works for interface symbols.\n\n"
                        f"💡 **What to do instead:**\n"
                        f"- If you want to see what '{interface.name}' **inherits from** or **uses**, "
                        f"use `get_symbol_context(symbol_id={interface_id}, include_relationships=true)`\n"
                        f"- If you want to see what **calls** '{interface.name}', "
                        f"use `find_callers(symbol_id={interface_id})`\n"
                        f"- If you want to find **methods** in '{interface.name}', "
                        f"use `list_symbols_in_file` with `symbol_kinds=[\"METHOD\"]`"
                    )
                )]
            
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
                return [TextContent(
                    type="text",
                    text=(
                        f"No implementations found for interface '{interface.name}'.\n\n"
                        f"This could mean:\n"
                        f"- The interface has no implementing classes in the codebase\n"
                        f"- The codebase hasn't been fully indexed yet\n"
                        f"- The implementations exist in external assemblies\n\n"
                        f"💡 Try using `get_symbol_context(symbol_id={interface_id})` to see relationships."
                    )
                )]
            
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



            
async def find_references(
    symbol_id: int,
    reference_type: Optional[str] = None,
    relationship_types: Optional[List[str]] = None,
    limit: int = 50,
) -> List[TextContent]:
    """
    Find all references to a symbol.

    Args:
        symbol_id: Symbol ID
        reference_type: Optional filter by type (single)
        relationship_types: Optional filter by relationship types (list)
        limit: Maximum results

    Returns:
        List of references
    """
    try:
        if symbol_id <= 0:
            return [TextContent(type="text", text="Invalid symbol_id: must be positive")]
        if limit < 1 or limit > 1000:
            limit = min(max(1, limit), 1000)

        async with get_readonly_session() as session:
            
            # Get the symbol
            result = await session.execute(
                select(Symbol).where(Symbol.id == symbol_id)
            )
            symbol = result.scalar_one_or_none()
            
            if not symbol:
                return [TextContent(type="text", text=f"Symbol ID {symbol_id} not found")]
            
            # Build query filters
            filters = [Relation.to_symbol_id == symbol_id]
            
            if reference_type and not relationship_types:
                try:
                    rel_type = RelationTypeEnum(reference_type.lower())
                    filters.append(Relation.relation_type == rel_type)
                except ValueError:
                    pass
            
            if relationship_types:
                valid_types = []
                # If reference_type was also provided, include it in valid_types
                if reference_type:
                    try:
                        valid_types.append(RelationTypeEnum(reference_type.lower()))
                    except ValueError:
                        pass
                for rt in relationship_types:
                    try:
                        valid_types.append(RelationTypeEnum[rt])
                    except KeyError:
                        logger.warning(f"Invalid relation type: {rt}")
                
                if valid_types:
                    filters.append(Relation.relation_type.in_(valid_types))

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
                # Task 11: Contextual Suggestions
                suggestions = []
                
                # Check for Controller
                # Use robust attribute checking
                is_controller = symbol.name.endswith("Controller")
                if not is_controller and symbol.attributes and isinstance(symbol.attributes, list):
                     is_controller = any(attr.get('name') == 'ApiController' for attr in symbol.attributes)

                if symbol.kind == SymbolKindEnum.CLASS and is_controller:
                   suggestions.append(f"💡 This looks like an API Controller. Try to find who calls the API using `find_api_endpoints`.")

                # Check for Interface
                if symbol.kind == SymbolKindEnum.INTERFACE:
                     suggestions.append(f"💡 To find classes implementing this interface, use `find_implementations(interface_id={symbol_id})`.")

                suggestion_text = "\n".join(suggestions)
                if suggestion_text:
                    suggestion_text = "\n\n" + suggestion_text
                    
                return [TextContent(type="text", text=f"No references found for '{symbol.name}'.{suggestion_text}")]
            
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
