"""
Call Graph Traversal Utility for Phase 3: Intelligent Traversal

This module provides production-ready call graph traversal capabilities for
exploring symbol relationships in depth. It supports both downstream (callees)
and upstream (callers) traversal with configurable depth, smart cycle detection,
and token budget management.

Key Features:
- Multi-level graph traversal with configurable depth
- Support for multiple relation types (CALLS, INHERITS, IMPLEMENTS, USES by default; IMPORTS, EXPORTS optional)
- Bidirectional traversal (downstream/upstream/both)
- Cycle detection and prevention
- Token budget tracking to prevent context overflow
- Smart pruning for large graphs
- Signature extraction for efficient representation
- Customizable relation types via parameter
"""

from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import deque
from enum import Enum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database.models import Symbol, Relation, File, Chunk
from src.config.enums import RelationTypeEnum, SymbolKindEnum
from src.utils.logging_config import get_logger
from src.utils.layer_detector import LayerDetector

logger = get_logger(__name__)


class TraversalDirection(str, Enum):
    """Direction for graph traversal."""
    DOWNSTREAM = "downstream"  # Follow outgoing edges (what this calls)
    UPSTREAM = "upstream"  # Follow incoming edges (what calls this)
    BOTH = "both"  # Follow both directions


@dataclass
class TraversalConfig:
    """Configuration for call graph traversal."""
    depth: int = 0  # Maximum depth to traverse (0 = no traversal)
    direction: TraversalDirection = TraversalDirection.DOWNSTREAM
    relation_types: List[RelationTypeEnum] = field(default_factory=lambda: [
        RelationTypeEnum.CALLS,
        RelationTypeEnum.INHERITS,
        RelationTypeEnum.IMPLEMENTS,
        RelationTypeEnum.USES,
    ])
    max_symbols: int = 50  # Maximum symbols to include in result
    max_tokens: int = 10000  # Maximum estimated tokens for result
    include_source_code: bool = True  # Include full code for root symbol
    include_signatures: bool = True  # Include signatures for related symbols
    deduplicate: bool = True  # Remove duplicate symbols in results
    # Optional: Layer-aware traversal
    allowed_layers: Optional[List[str]] = None  # If set, only traverse symbols in these layers
    excluded_layers: Optional[List[str]] = None  # If set, skip symbols in these layers
    # Optional: Confidence scoring
    include_confidence: bool = False  # Calculate and include confidence scores
    # Optional: External dependencies
    include_external_deps: bool = False  # Include symbols from external packages
    # Optional: .NET DI Interface Resolution
    resolve_interfaces: bool = True  # Automatically resolve interface calls to implementations
    # Optional: CQRS/MediatR Pattern Detection
    detect_cqrs_handlers: bool = True  # Detect and follow MediatR-style command/query handlers


@dataclass
class SymbolNode:
    """Represents a symbol in the traversal graph."""
    symbol_id: int
    name: str
    fully_qualified_name: Optional[str]
    kind: str
    signature: Optional[str]
    documentation: Optional[str]
    file_path: str
    start_line: int
    end_line: int
    depth: int  # Depth level from root (0 = root)
    relation_type: Optional[str] = None  # How this symbol relates to parent
    source_code: Optional[str] = None  # Full code (only for root usually)
    token_estimate: int = 0  # Estimated token count
    
    # Additional metadata
    access_modifier: Optional[str] = None
    return_type: Optional[str] = None
    parameters: Optional[List[Dict]] = None
    complexity: Optional[int] = None
    
    # Optional enhancements
    layer: Optional[str] = None  # Architectural layer (Controller, Service, etc.)
    confidence_score: Optional[float] = None  # Confidence score for relationship (0.0-1.0)
    is_external: bool = False  # True if from external package


@dataclass
class TraversalResult:
    """Result of call graph traversal."""
    root_symbol: SymbolNode
    related_symbols: List[SymbolNode] = field(default_factory=list)
    total_symbols: int = 0
    total_tokens: int = 0
    max_depth_reached: int = 0
    was_truncated: bool = False  # True if result was limited by max_symbols/max_tokens
    cycles_detected: int = 0  # Number of cycles detected and prevented
    interface_resolutions: int = 0  # Number of interface->implementation resolutions
    cqrs_handlers_found: int = 0  # Number of CQRS handlers detected


class CallGraphTraverser:
    """
    Production-ready call graph traversal engine.
    
    This class provides comprehensive graph traversal capabilities with
    smart pruning, cycle detection, and token budget management.
    
    Example Usage:
        traverser = CallGraphTraverser(session)
        config = TraversalConfig(depth=2, direction=TraversalDirection.DOWNSTREAM)
        result = await traverser.traverse(symbol_id=123, config=config)
    """
    
    def __init__(self, session: AsyncSession, enable_cache: bool = True):
        """
        Initialize traverser with database session.
        
        Args:
            session: SQLAlchemy async session for database queries
            enable_cache: Enable caching for frequently traversed paths
        """
        self.session = session
        self._visited: Set[int] = set()  # Track visited symbols to prevent cycles
        self._token_budget = 0  # Current token count
        self._symbol_count = 0  # Current symbol count
        self._enable_cache = enable_cache
        self._cache: Dict[Tuple[int, int, str], List[Tuple[int, str]]] = {}  # Cache for relation queries
    
    async def traverse(
        self,
        symbol_id: int,
        config: TraversalConfig
    ) -> Optional[TraversalResult]:
        """
        Traverse the call graph starting from a symbol.
        
        Args:
            symbol_id: Starting symbol ID
            config: Traversal configuration
            
        Returns:
            TraversalResult with root and related symbols, or None if symbol not found
        """
        # Reset state
        self._visited = set()
        self._token_budget = 0
        self._symbol_count = 0
        
        # Get root symbol
        root_node = await self._fetch_symbol_node(symbol_id, depth=0, include_code=config.include_source_code)
        if not root_node:
            logger.warning("symbol_not_found_for_traversal", symbol_id=symbol_id)
            return None
        
        self._visited.add(symbol_id)
        self._token_budget += root_node.token_estimate
        self._symbol_count += 1
        
        result = TraversalResult(
            root_symbol=root_node,
            related_symbols=[],
            total_symbols=1,
            total_tokens=root_node.token_estimate,
            max_depth_reached=0,
        )
        
        # If depth is 0, return just the root
        if config.depth == 0:
            return result
        
        # Perform BFS traversal
        cycles_detected = await self._traverse_graph(
            root_symbol_id=symbol_id,
            config=config,
            result=result
        )
        
        result.cycles_detected = cycles_detected
        result.total_symbols = self._symbol_count
        result.total_tokens = self._token_budget
        
        logger.info(
            "call_graph_traversal_complete",
            root_symbol_id=symbol_id,
            total_symbols=result.total_symbols,
            max_depth=result.max_depth_reached,
            cycles_detected=cycles_detected,
            was_truncated=result.was_truncated,
        )
        
        return result
    
    async def _traverse_graph(
        self,
        root_symbol_id: int,
        config: TraversalConfig,
        result: TraversalResult
    ) -> int:
        """
        Perform breadth-first traversal of the graph.
        
        Args:
            root_symbol_id: Starting symbol ID
            config: Traversal configuration
            result: Result object to populate
            
        Returns:
            Number of cycles detected
        """
        cycles_detected = 0
        queue: deque[Tuple[int, int, Optional[str]]] = deque()  # (symbol_id, current_depth, relation_type)
        
        # Initialize queue with direct relations from root
        initial_relations = await self._get_relations(root_symbol_id, config)
        for related_id, relation_type in initial_relations:
            queue.append((related_id, 1, relation_type))
        
        while queue:
            symbol_id, current_depth, relation_type = queue.popleft()
            
            # Check if we've exceeded depth limit
            if current_depth > config.depth:
                continue
            
            # Check if we've already visited (cycle detection)
            if symbol_id in self._visited:
                cycles_detected += 1
                continue
            
            # Check budget limits
            if self._symbol_count >= config.max_symbols:
                result.was_truncated = True
                logger.debug("traversal_truncated_by_symbol_count", max_symbols=config.max_symbols)
                break
            
            if self._token_budget >= config.max_tokens:
                result.was_truncated = True
                logger.debug("traversal_truncated_by_token_budget", max_tokens=config.max_tokens)
                break
            
             # Fetch symbol node (without full code, just signature)
            node = await self._fetch_symbol_node(
                symbol_id=symbol_id,
                depth=current_depth,
                include_code=False,  # Only include signatures for related symbols
                relation_type=relation_type,
                config=config
            )
            
            if not node:
                continue
            
            # Layer filtering
            if config.allowed_layers and node.layer and node.layer not in config.allowed_layers:
                continue
            if config.excluded_layers and node.layer and node.layer in config.excluded_layers:
                continue
            
            # Skip external dependencies if not included
            if node.is_external and not config.include_external_deps:
                continue
            
            # Add to visited and update budgets
            self._visited.add(symbol_id)
            self._token_budget += node.token_estimate
            self._symbol_count += 1
            
            # Add to result
            result.related_symbols.append(node)
            result.max_depth_reached = max(result.max_depth_reached, current_depth)
            
            # If we haven't reached max depth, add this symbol's relations to queue
            if current_depth < config.depth:
                next_relations = await self._get_relations(symbol_id, config)
                for related_id, rel_type in next_relations:
                    queue.append((related_id, current_depth + 1, rel_type))
                
                # NEW: Interface Resolution for .NET DI Tracing
                if config.resolve_interfaces:
                    # Get the actual symbol object to check if it's an interface
                    symbol_result = await self.session.execute(
                        select(Symbol).where(Symbol.id == symbol_id)
                    )
                    symbol_obj = symbol_result.scalar_one_or_none()
                    
                    if symbol_obj:
                        implementations = await self._resolve_interface_implementations(symbol_id, symbol_obj)
                        for impl_id in implementations:
                            if impl_id not in self._visited:
                                queue.append((impl_id, current_depth + 1, f"IMPLEMENTS_{relation_type}"))
                                result.interface_resolutions += 1
                
                # NEW: CQRS Handler Detection
                if config.detect_cqrs_handlers:
                    symbol_result = await self.session.execute(
                        select(Symbol).where(Symbol.id == symbol_id)
                    )
                    symbol_obj = symbol_result.scalar_one_or_none()
                    
                    if symbol_obj:
                        handler_id = await self._detect_cqrs_handler(symbol_id, symbol_obj)
                        if handler_id and handler_id not in self._visited:
                            queue.append((handler_id, current_depth + 1, "CQRS_HANDLER"))
                            result.cqrs_handlers_found += 1

        
        return cycles_detected
    
    async def _get_relations(
        self,
        symbol_id: int,
        config: TraversalConfig
    ) -> List[Tuple[int, str]]:
        """
        Get related symbol IDs based on configuration.
        
        Args:
            symbol_id: Symbol to get relations for
            config: Traversal configuration
            
        Returns:
            List of (related_symbol_id, relation_type) tuples
        """
        # Check cache first
        cache_key = (symbol_id, config.depth, config.direction.value)
        if self._enable_cache and cache_key in self._cache:
            return self._cache[cache_key]
        
        relations = []
        
        def get_relation_type_str(rel_type) -> str:
            """Safely get string value from relation type (handles both enum and string)."""
            if hasattr(rel_type, 'value'):
                return str(rel_type.value)
            return str(rel_type)
        
        # Get downstream relations (what this symbol calls/uses)
        if config.direction in [TraversalDirection.DOWNSTREAM, TraversalDirection.BOTH]:
            try:
                result = await self.session.execute(
                    select(Relation.to_symbol_id, Relation.relation_type)
                    .where(Relation.from_symbol_id == symbol_id)
                    .where(Relation.relation_type.in_(config.relation_types))
                )
                for to_id, rel_type in result.all():
                    relations.append((to_id, get_relation_type_str(rel_type)))
            except Exception as e:
                logger.warning(f"Error fetching downstream relations for symbol {symbol_id}: {e}")
        
        # Get upstream relations (what calls/uses this symbol)
        if config.direction in [TraversalDirection.UPSTREAM, TraversalDirection.BOTH]:
            try:
                result = await self.session.execute(
                    select(Relation.from_symbol_id, Relation.relation_type)
                    .where(Relation.to_symbol_id == symbol_id)
                    .where(Relation.relation_type.in_(config.relation_types))
                )
                for from_id, rel_type in result.all():
                    relations.append((from_id, f"CALLED_BY_{get_relation_type_str(rel_type)}"))
            except Exception as e:
                logger.warning(f"Error fetching upstream relations for symbol {symbol_id}: {e}")
        
        # Cache the result
        if self._enable_cache:
            self._cache[cache_key] = relations
        
        return relations
    
    async def _fetch_symbol_node(
        self,
        symbol_id: int,
        depth: int,
        include_code: bool = False,
        relation_type: Optional[str] = None,
        config: Optional[TraversalConfig] = None
    ) -> Optional[SymbolNode]:
        """
        Fetch symbol data and create SymbolNode.
        
        Args:
            symbol_id: Symbol ID to fetch
            depth: Depth level in traversal
            include_code: Whether to include full source code
            relation_type: How this symbol relates to its parent
            
        Returns:
            SymbolNode or None if not found
        """
        # Get symbol with file info
        result = await self.session.execute(
            select(Symbol, File)
            .join(File, Symbol.file_id == File.id)
            .where(Symbol.id == symbol_id)
        )
        row = result.first()
        
        if not row:
            return None
        
        symbol, file = row
        
        # Helper to safely get enum value
        def get_enum_value(enum_val):
            """Safely get string value from enum (handles both enum and string)."""
            if enum_val is None:
                return None
            if hasattr(enum_val, 'value'):
                return str(enum_val.value)
            return str(enum_val)
        
        # Detect layer
        layer = LayerDetector.detect_layer(symbol, file)
        
        # Detect if external (simple heuristic: if file path contains common package indicators)
        is_external = self._is_external_symbol(file.path, symbol.fully_qualified_name or "")
        
        # Calculate confidence score if requested
        confidence_score = None
        if config and config.include_confidence:
            confidence_score = self._calculate_confidence(symbol, file, relation_type)
        
        # Create base node
        node = SymbolNode(
            symbol_id=symbol.id,
            name=symbol.name,
            fully_qualified_name=symbol.fully_qualified_name,
            kind=get_enum_value(symbol.kind) or "unknown",
            signature=symbol.signature,
            documentation=symbol.documentation,
            file_path=file.path,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            depth=depth,
            relation_type=relation_type,
            access_modifier=get_enum_value(symbol.access_modifier),
            return_type=symbol.return_type,
            parameters=symbol.parameters,
            complexity=symbol.complexity,
            layer=layer,
            confidence_score=confidence_score,
            is_external=is_external,
        )
        
        # Include source code if requested
        if include_code:
            source_code = await self._fetch_source_code(symbol_id)
            if source_code:
                node.source_code = source_code
                node.token_estimate = len(source_code) // 4  # Rough estimate: 1 token ≈ 4 chars
            else:
                # Fallback: estimate from signature
                node.token_estimate = len(node.signature or "") // 4 if node.signature else 50
        else:
            # For signatures only, much smaller token estimate
            sig_length = len(node.signature or "")
            doc_length = len(node.documentation or "") if node.documentation and len(node.documentation) < 200 else 0
            node.token_estimate = (sig_length + doc_length) // 4 or 20
        
        return node
    
    async def _fetch_source_code(self, symbol_id: int) -> Optional[str]:
        """
        Fetch source code for a symbol from chunks.
        
        Args:
            symbol_id: Symbol ID
            
        Returns:
            Source code string or None
        """
        result = await self.session.execute(
            select(Chunk.content)
            .where(Chunk.symbol_id == symbol_id)
            .order_by(Chunk.id)
            .limit(1)
        )
        row = result.first()
        return row[0] if row else None
    
    def _is_external_symbol(self, file_path: str, fqn: str) -> bool:
        """
        Determine if a symbol is from an external package.
        
        Args:
            file_path: File path of the symbol
            fqn: Fully qualified name
            
        Returns:
            True if external, False otherwise
        """
        external_indicators = [
            '.dll',  # .NET assemblies
            'node_modules/',  # npm packages
            'site-packages/',  # Python packages
            'System.',  # .NET framework
            'Microsoft.',  # Microsoft libraries
            'Newtonsoft.',  # Common .NET library
            'EntityFramework',  # EF
        ]
        
        file_path_lower = file_path.lower()
        fqn_lower = fqn.lower()
        
        return any(indicator.lower() in file_path_lower or indicator.lower() in fqn_lower 
                   for indicator in external_indicators)
    
    def _calculate_confidence(self, symbol: Symbol, file: File, relation_type: Optional[str]) -> float:
        """
        Calculate confidence score for a symbol relationship.
        
        Args:
            symbol: Symbol object
            file: File object
            relation_type: Type of relationship
            
        Returns:
            Confidence score (0.0-1.0)
        """
        confidence = 0.5  # Base confidence
        
        # Higher confidence if has signature
        if symbol.signature:
            confidence += 0.1
        
        # Higher confidence if has documentation
        if symbol.documentation:
            confidence += 0.1
        
        # Higher confidence for CALLS relationships (most reliable)
        if relation_type and 'CALL' in relation_type.upper():
            confidence += 0.2
        
        # Higher confidence if symbol is in a standard location
        standard_paths = ['controllers/', 'services/', 'repositories/', 'models/']
        if any(path in file.path.lower() for path in standard_paths):
            confidence += 0.1
        
        # Cap at 1.0
        return min(confidence, 1.0)
    
    async def _resolve_interface_implementations(
        self,
        symbol_id: int,
        symbol: Symbol
    ) -> List[int]:
        """
        Resolve an interface or abstract class to its concrete implementations.
        
        This is critical for .NET DI tracing where controllers depend on interfaces
        (e.g., IUserService) but we need to trace into the actual implementation
        (e.g., UserService).
        
        Args:
            symbol_id: Symbol ID of the interface/abstract class
            symbol: Symbol object to check if it's an interface
            
        Returns:
            List of symbol IDs that implement/inherit from this interface
        """
        # Case 1: Symbol is a METHOD (e.g., IUserService.GetUser)
        # We need to find the parent Interface, resolve its implementations, then find the matching method
        if symbol.kind == SymbolKindEnum.METHOD:
            return await self._resolve_interface_method_implementations(symbol_id, symbol)

        # Case 2: Symbol is an INTERFACE or CLASS
        # Check if this is an interface or abstract class
        if symbol.kind not in [SymbolKindEnum.INTERFACE, SymbolKindEnum.CLASS]:
            return []
        
        # If it's a class, check if it's abstract
        is_abstract = False
        if symbol.kind == SymbolKindEnum.CLASS:
            if symbol.structured_docs:
                roslyn_data = symbol.structured_docs.get('roslyn', {})
                is_abstract = roslyn_data.get('is_abstract', False) or symbol.structured_docs.get('is_abstract', False)
            if not is_abstract:
                return []  # Concrete class, no need to resolve
        
        # Find all symbols that IMPLEMENT (for interfaces) or INHERIT (for abstract classes) from this symbol
        try:
            if symbol.kind == SymbolKindEnum.INTERFACE:
                # Query for IMPLEMENTS relations
                result = await self.session.execute(
                    select(Relation.from_symbol_id)
                    .where(
                        Relation.to_symbol_id == symbol_id,
                        Relation.relation_type == RelationTypeEnum.IMPLEMENTS
                    )
                )
            else:
                # Abstract class: query for INHERITS relations
                result = await self.session.execute(
                    select(Relation.from_symbol_id)
                    .where(
                        Relation.to_symbol_id == symbol_id,
                        Relation.relation_type == RelationTypeEnum.INHERITS
                    )
                )
            
            implementation_ids = [row[0] for row in result.all()]
            
            if implementation_ids:
                logger.debug(
                    "interface_resolved",
                    interface_id=symbol_id,
                    interface_name=symbol.name,
                    implementations_count=len(implementation_ids)
                )
            
            return implementation_ids
        except Exception as e:
            logger.warning(f"Error resolving interface implementations for {symbol.name}: {e}")
            return []

    async def _resolve_interface_method_implementations(
        self,
        method_id: int,
        method_symbol: Symbol
    ) -> List[int]:
        """
        Resolve an interface method to its concrete implementations.
        
        Args:
            method_id: Symbol ID of the interface method
            method_symbol: Symbol object
            
        Returns:
            List of method symbol IDs that implement this interface method
        """
        try:
            # 1. Find the parent Interface/Class
            parent_id = method_symbol.parent_symbol_id
            
            if not parent_id:
                # Try to find via file structure if parent_symbol_id is missing
                # This is a fallback and might be expensive/complex
                return []
            
            # Get parent symbol
            parent_result = await self.session.execute(
                select(Symbol).where(Symbol.id == parent_id)
            )
            parent_symbol = parent_result.scalar_one_or_none()
            
            if not parent_symbol:
                return []
            
            # 2. Resolve the parent's implementations
            # This calls the main method recursively, but now with an Interface/Class
            impl_class_ids = await self._resolve_interface_implementations(parent_id, parent_symbol)
            
            if not impl_class_ids:
                return []
            
            # 3. Find matching methods in the implementing classes
            # We look for methods with the same name in the implementing classes
            # TODO: Match signature/parameters for better accuracy (overloading support)
            
            result = await self.session.execute(
                select(Symbol.id)
                .where(
                    Symbol.parent_symbol_id.in_(impl_class_ids),
                    Symbol.kind == SymbolKindEnum.METHOD,
                    Symbol.name == method_symbol.name
                )
            )
            
            impl_method_ids = [row[0] for row in result.all()]
            
            if impl_method_ids:
                logger.debug(
                    "interface_method_resolved",
                    interface_method=method_symbol.name,
                    parent_interface=parent_symbol.name,
                    implementations_count=len(impl_method_ids)
                )
            
            return impl_method_ids
            
        except Exception as e:
            logger.warning(f"Error resolving interface method implementations for {method_symbol.name}: {e}")
            return []
    
    async def _detect_cqrs_handler(
        self,
        symbol_id: int,
        symbol: Symbol
    ) -> Optional[int]:
        """
        Detect if a symbol is a MediatR-style command/query and find its handler.
        
        Patterns detected:
        - Classes implementing IRequest<TResponse> (commands/queries)
        - Methods calling _mediator.Send(command) or similar
        
        Args:
            symbol_id: Symbol ID to check
            symbol: Symbol object
            
        Returns:
            Handler symbol ID if found, None otherwise
        """
        # Check if this symbol implements IRequest or ICommand or IQuery
        if symbol.kind not in [SymbolKindEnum.CLASS, SymbolKindEnum.METHOD]:
            return None
        
        try:
            # Strategy 1: If this is a Request class, find its handler
            if symbol.kind == SymbolKindEnum.CLASS:
                # Check if it implements IRequest, ICommand, or IQuery
                request_interfaces = ['IRequest', 'ICommand', 'IQuery']
                
                # Get base types from structured_docs
                if symbol.structured_docs:
                    roslyn_data = symbol.structured_docs.get('roslyn', {})
                    interfaces = roslyn_data.get('interfaces', [])
                    
                    # Check if any interface matches MediatR patterns
                    is_request = any(
                        any(req_type in iface for req_type in request_interfaces)
                        for iface in interfaces
                    )
                    
                    if is_request:
                        # Find handler: look for IRequestHandler<ThisCommand, TResponse>
                        # This is simplified - a full implementation would parse generic types
                        handler_name = f"{symbol.name}Handler"
                        
                        # Query for a symbol with that name
                        result = await self.session.execute(
                            select(Symbol.id)
                            .where(Symbol.name == handler_name)
                        )
                        handler_row = result.first()
                        
                        if handler_row:
                            logger.debug(
                                "cqrs_handler_detected",
                                request_class=symbol.name,
                                handler_class=handler_name
                            )
                            return handler_row[0]
            
            return None
        except Exception as e:
            logger.warning(f"Error detecting CQRS handler for {symbol.name}: {e}")
            return None
    
    def format_result_markdown(self, result: TraversalResult, include_stats: bool = True) -> str:
        """
        Format traversal result as markdown.
        
        Args:
            result: Traversal result to format
            include_stats: Whether to include statistics header
            
        Returns:
            Formatted markdown string
        """
        lines = []
        
        if include_stats:
            lines.append("# Call Graph Traversal Result\n")
            lines.append(f"**Statistics**: {result.total_symbols} symbols, "
                        f"max depth {result.max_depth_reached}, "
                        f"~{result.total_tokens} tokens\n")
            if result.interface_resolutions > 0:
                lines.append(f"🔗 **Interface Resolutions**: {result.interface_resolutions} (DI tracing)\n")
            if result.cqrs_handlers_found > 0:
                lines.append(f"📨 **CQRS Handlers**: {result.cqrs_handlers_found}\n")
            if result.was_truncated:
                lines.append("⚠️ *Result was truncated due to size limits*\n")
            if result.cycles_detected > 0:
                lines.append(f"🔄 *{result.cycles_detected} cycle(s) detected and prevented*\n")
            lines.append("\n---\n\n")
        
        # Root symbol (with full code)
        lines.append(f"## Root: {result.root_symbol.name} ({result.root_symbol.kind})\n\n")
        lines.append(f"**Location**: `{result.root_symbol.file_path}` "
                    f"(lines {result.root_symbol.start_line}-{result.root_symbol.end_line})\n")
        lines.append(f"**ID**: {result.root_symbol.symbol_id}\n")
        
        if result.root_symbol.signature:
            lines.append(f"**Signature**: `{result.root_symbol.signature}`\n")
        
        if result.root_symbol.documentation:
            doc = result.root_symbol.documentation[:200]
            if len(result.root_symbol.documentation) > 200:
                doc += "..."
            lines.append(f"**Documentation**: {doc}\n")
        
        if result.root_symbol.source_code:
            lines.append("\n**Implementation**:\n")
            lines.append("```\n")
            lines.append(result.root_symbol.source_code)
            lines.append("\n```\n")
        
        lines.append("\n---\n\n")
        
        # Related symbols (grouped by depth)
        if result.related_symbols:
            lines.append("## Related Symbols\n\n")
            
            # Group by depth
            by_depth: Dict[int, List[SymbolNode]] = {}
            for node in result.related_symbols:
                if node.depth not in by_depth:
                    by_depth[node.depth] = []
                by_depth[node.depth].append(node)
            
            # Output by depth level
            for depth in sorted(by_depth.keys()):
                nodes = by_depth[depth]
                lines.append(f"### Depth {depth} ({len(nodes)} symbols)\n\n")
                
                for node in nodes:
                    relation = node.relation_type or "RELATED"
                    lines.append(f"#### {node.name} ({node.kind}) [{relation}]\n\n")
                    lines.append(f"- **ID**: {node.symbol_id}\n")
                    lines.append(f"- **Location**: `{node.file_path}:{node.start_line}-{node.end_line}`\n")
                    
                    if node.signature:
                        lines.append(f"- **Signature**: `{node.signature}`\n")
                    
                    if node.documentation:
                        doc = node.documentation[:150]
                        if len(node.documentation) > 150:
                            doc += "..."
                        lines.append(f"- **Doc**: {doc}\n")
                    
                    lines.append("\n")
        
        return "".join(lines)

