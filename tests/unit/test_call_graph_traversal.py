"""
Unit tests for Call Graph Traversal (Phase 3: Intelligent Traversal).

These tests verify the production-ready call graph traversal implementation,
including depth traversal, cycle detection, direction control, and token budgeting.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from src.utils.call_graph_traversal import (
    CallGraphTraverser,
    TraversalConfig,
    TraversalDirection,
    TraversalResult,
    SymbolNode,
)
from src.config.enums import RelationTypeEnum, SymbolKindEnum, AccessModifierEnum
from src.database.models import Symbol, File, Relation, Chunk


class TestTraversalConfig:
    """Test TraversalConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = TraversalConfig()
        assert config.depth == 0
        assert config.direction == TraversalDirection.DOWNSTREAM
        assert RelationTypeEnum.CALLS in config.relation_types
        assert RelationTypeEnum.INHERITS in config.relation_types
        assert config.max_symbols == 50
        assert config.max_tokens == 10000
        assert config.include_source_code is True
        assert config.include_signatures is True
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = TraversalConfig(
            depth=3,
            direction=TraversalDirection.UPSTREAM,
            max_symbols=100,
            max_tokens=20000,
        )
        assert config.depth == 3
        assert config.direction == TraversalDirection.UPSTREAM
        assert config.max_symbols == 100
        assert config.max_tokens == 20000


class TestSymbolNode:
    """Test SymbolNode dataclass."""
    
    def test_symbol_node_creation(self):
        """Test creating a symbol node."""
        node = SymbolNode(
            symbol_id=1,
            name="TestFunction",
            fully_qualified_name="MyClass.TestFunction",
            kind="FUNCTION",
            signature="def TestFunction(x: int) -> str",
            documentation="Test function docs",
            file_path="test.py",
            start_line=10,
            end_line=20,
            depth=0,
        )
        assert node.symbol_id == 1
        assert node.name == "TestFunction"
        assert node.depth == 0
        assert node.source_code is None


class TestCallGraphTraverser:
    """Test CallGraphTraverser class."""
    
    @pytest.fixture
    def mock_session(self):
        """Create mock async session."""
        session = AsyncMock(spec=AsyncSession)
        return session
    
    @pytest.fixture
    def traverser(self, mock_session):
        """Create traverser instance."""
        return CallGraphTraverser(mock_session)
    
    @pytest.fixture
    def mock_symbol(self):
        """Create mock symbol."""
        symbol = MagicMock(spec=Symbol)
        symbol.id = 1
        symbol.name = "TestFunction"
        symbol.fully_qualified_name = "MyClass.TestFunction"
        symbol.kind = SymbolKindEnum.FUNCTION
        symbol.signature = "def TestFunction(x: int) -> str"
        symbol.documentation = "Test function"
        symbol.start_line = 10
        symbol.end_line = 20
        symbol.access_modifier = AccessModifierEnum.PUBLIC
        symbol.return_type = "str"
        symbol.parameters = [{"name": "x", "type": "int"}]
        symbol.complexity = 5
        return symbol
    
    @pytest.fixture
    def mock_file(self):
        """Create mock file."""
        file = MagicMock(spec=File)
        file.id = 1
        file.path = "test/module.py"
        return file
    
    @pytest.mark.asyncio
    async def test_traverse_depth_zero(self, traverser, mock_session, mock_symbol, mock_file):
        """Test traversal with depth=0 returns only root symbol."""
        # Mock database queries
        mock_result = MagicMock()
        mock_result.first.return_value = (mock_symbol, mock_file)
        mock_session.execute.return_value = mock_result
        
        # Mock chunk query
        mock_chunk_result = MagicMock()
        mock_chunk_result.first.return_value = ("def TestFunction(x: int) -> str:\n    return str(x)",)
        
        async def execute_side_effect(*args, **kwargs):
            # First call: symbol + file
            # Second call: chunk
            if mock_session.execute.call_count == 1:
                return mock_result
            else:
                return mock_chunk_result
        
        mock_session.execute.side_effect = execute_side_effect
        
        config = TraversalConfig(depth=0)
        result = await traverser.traverse(symbol_id=1, config=config)
        
        assert result is not None
        assert result.root_symbol.symbol_id == 1
        assert result.root_symbol.name == "TestFunction"
        assert result.total_symbols == 1
        assert len(result.related_symbols) == 0
        assert result.max_depth_reached == 0
    
    @pytest.mark.asyncio
    async def test_traverse_downstream_depth_one(self, traverser, mock_session, mock_symbol, mock_file):
        """Test downstream traversal with depth=1."""
        # Mock root symbol query
        root_symbol = mock_symbol
        called_symbol = MagicMock(spec=Symbol)
        called_symbol.id = 2
        called_symbol.name = "CalledFunction"
        called_symbol.fully_qualified_name = "Utils.CalledFunction"
        called_symbol.kind = SymbolKindEnum.FUNCTION
        called_symbol.signature = "def CalledFunction() -> None"
        called_symbol.documentation = "Called function"
        called_symbol.start_line = 50
        called_symbol.end_line = 55
        called_symbol.access_modifier = AccessModifierEnum.PUBLIC
        called_symbol.return_type = "None"
        called_symbol.parameters = []
        called_symbol.complexity = 2
        
        call_count = [0]
        
        async def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            
            if call_count[0] == 1:
                # First: Get root symbol
                mock_result = MagicMock()
                mock_result.first.return_value = (root_symbol, mock_file)
                return mock_result
            elif call_count[0] == 2:
                # Second: Get root source code
                mock_result = MagicMock()
                mock_result.first.return_value = ("def TestFunction():\n    CalledFunction()",)
                return mock_result
            elif call_count[0] == 3:
                # Third: Get relations from root
                mock_result = MagicMock()
                mock_result.all.return_value = [(2, RelationTypeEnum.CALLS)]
                return mock_result
            elif call_count[0] == 4:
                # Fourth: Get called symbol
                mock_result = MagicMock()
                mock_result.first.return_value = (called_symbol, mock_file)
                return mock_result
            elif call_count[0] == 5:
                # Fifth: Get called symbol code (not needed for non-root)
                mock_result = MagicMock()
                mock_result.first.return_value = None
                return mock_result
        
        mock_session.execute.side_effect = execute_side_effect
        
        config = TraversalConfig(depth=1, direction=TraversalDirection.DOWNSTREAM)
        result = await traverser.traverse(symbol_id=1, config=config)
        
        assert result is not None
        assert result.total_symbols == 2
        assert len(result.related_symbols) == 1
        assert result.related_symbols[0].symbol_id == 2
        assert result.related_symbols[0].name == "CalledFunction"
        assert result.related_symbols[0].depth == 1
        assert result.max_depth_reached == 1
    
    @pytest.mark.asyncio
    async def test_traverse_upstream_depth_one(self, traverser, mock_session, mock_symbol, mock_file):
        """Test upstream traversal (what calls this symbol)."""
        # Mock root symbol
        root_symbol = mock_symbol
        caller_symbol = MagicMock(spec=Symbol)
        caller_symbol.id = 3
        caller_symbol.name = "CallerFunction"
        caller_symbol.fully_qualified_name = "App.CallerFunction"
        caller_symbol.kind = SymbolKindEnum.FUNCTION
        caller_symbol.signature = "def CallerFunction() -> None"
        caller_symbol.documentation = "Caller function"
        caller_symbol.start_line = 100
        caller_symbol.end_line = 110
        caller_symbol.access_modifier = AccessModifierEnum.PUBLIC
        caller_symbol.return_type = "None"
        caller_symbol.parameters = []
        caller_symbol.complexity = 3
        
        call_count = [0]
        
        async def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            
            if call_count[0] == 1:
                # Get root symbol
                mock_result = MagicMock()
                mock_result.first.return_value = (root_symbol, mock_file)
                return mock_result
            elif call_count[0] == 2:
                # Get root source code
                mock_result = MagicMock()
                mock_result.first.return_value = ("def TestFunction():\n    pass",)
                return mock_result
            elif call_count[0] == 3:
                # Get upstream relations (what calls this)
                mock_result = MagicMock()
                mock_result.all.return_value = [(3, RelationTypeEnum.CALLS)]
                return mock_result
            elif call_count[0] == 4:
                # Get caller symbol
                mock_result = MagicMock()
                mock_result.first.return_value = (caller_symbol, mock_file)
                return mock_result
        
        mock_session.execute.side_effect = execute_side_effect
        
        config = TraversalConfig(depth=1, direction=TraversalDirection.UPSTREAM)
        result = await traverser.traverse(symbol_id=1, config=config)
        
        assert result is not None
        assert result.total_symbols == 2
        assert len(result.related_symbols) == 1
        assert result.related_symbols[0].symbol_id == 3
        assert result.related_symbols[0].name == "CallerFunction"
    
    @pytest.mark.asyncio
    async def test_cycle_detection(self, traverser, mock_session, mock_symbol, mock_file):
        """Test that cycles are detected and prevented."""
        # Create a cycle: A -> B -> A
        symbol_a = mock_symbol
        symbol_a.id = 1
        symbol_a.name = "FunctionA"
        
        symbol_b = MagicMock(spec=Symbol)
        symbol_b.id = 2
        symbol_b.name = "FunctionB"
        symbol_b.fully_qualified_name = "Module.FunctionB"
        symbol_b.kind = SymbolKindEnum.FUNCTION
        symbol_b.signature = "def FunctionB() -> None"
        symbol_b.documentation = "Function B"
        symbol_b.start_line = 30
        symbol_b.end_line = 35
        symbol_b.access_modifier = AccessModifierEnum.PUBLIC
        symbol_b.return_type = "None"
        symbol_b.parameters = []
        symbol_b.complexity = 1
        
        call_count = [0]
        
        async def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            
            if call_count[0] == 1:
                # Get root symbol A
                mock_result = MagicMock()
                mock_result.first.return_value = (symbol_a, mock_file)
                return mock_result
            elif call_count[0] == 2:
                # Get root source code
                mock_result = MagicMock()
                mock_result.first.return_value = ("def FunctionA():\n    FunctionB()",)
                return mock_result
            elif call_count[0] == 3:
                # A calls B
                mock_result = MagicMock()
                mock_result.all.return_value = [(2, RelationTypeEnum.CALLS)]
                return mock_result
            elif call_count[0] == 4:
                # Get symbol B
                mock_result = MagicMock()
                mock_result.first.return_value = (symbol_b, mock_file)
                return mock_result
            elif call_count[0] == 5:
                # B calls A (cycle!)
                mock_result = MagicMock()
                mock_result.all.return_value = [(1, RelationTypeEnum.CALLS)]
                return mock_result
        
        mock_session.execute.side_effect = execute_side_effect
        
        config = TraversalConfig(depth=2, direction=TraversalDirection.DOWNSTREAM)
        result = await traverser.traverse(symbol_id=1, config=config)
        
        assert result is not None
        assert result.cycles_detected >= 1
        # Should have A and B, but not A again
        assert result.total_symbols == 2
    
    @pytest.mark.asyncio
    async def test_max_symbols_truncation(self, traverser, mock_session, mock_symbol, mock_file):
        """Test that traversal respects max_symbols limit."""
        # Set max_symbols to 2 (root + 1 related)
        config = TraversalConfig(
            depth=2,
            direction=TraversalDirection.DOWNSTREAM,
            max_symbols=2,
        )
        
        # Mock multiple symbols
        call_count = [0]
        
        async def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            
            if call_count[0] == 1:
                # Get root
                mock_result = MagicMock()
                mock_result.first.return_value = (mock_symbol, mock_file)
                return mock_result
            elif call_count[0] == 2:
                # Get root code
                mock_result = MagicMock()
                mock_result.first.return_value = ("def test():\n    pass",)
                return mock_result
            elif call_count[0] == 3:
                # Return 3 relations (should be truncated to 1)
                mock_result = MagicMock()
                mock_result.all.return_value = [
                    (2, RelationTypeEnum.CALLS),
                    (3, RelationTypeEnum.CALLS),
                    (4, RelationTypeEnum.CALLS),
                ]
                return mock_result
            else:
                # Return symbols
                symbol = MagicMock(spec=Symbol)
                symbol.id = call_count[0] - 2
                symbol.name = f"Function{symbol.id}"
                symbol.fully_qualified_name = f"Module.Function{symbol.id}"
                symbol.kind = SymbolKindEnum.FUNCTION
                symbol.signature = f"def Function{symbol.id}() -> None"
                symbol.documentation = f"Function {symbol.id}"
                symbol.start_line = 10 * symbol.id
                symbol.end_line = 10 * symbol.id + 5
                symbol.access_modifier = AccessModifierEnum.PUBLIC
                symbol.return_type = "None"
                symbol.parameters = []
                symbol.complexity = 1
                
                mock_result = MagicMock()
                mock_result.first.return_value = (symbol, mock_file)
                return mock_result
        
        mock_session.execute.side_effect = execute_side_effect
        
        result = await traverser.traverse(symbol_id=1, config=config)
        
        assert result is not None
        assert result.total_symbols <= 2
        assert result.was_truncated is True
    
    @pytest.mark.asyncio
    async def test_format_result_markdown(self, traverser):
        """Test markdown formatting of traversal results."""
        root = SymbolNode(
            symbol_id=1,
            name="RootFunction",
            fully_qualified_name="App.RootFunction",
            kind="FUNCTION",
            signature="def RootFunction() -> None",
            documentation="Root function docs",
            file_path="app.py",
            start_line=10,
            end_line=20,
            depth=0,
            source_code="def RootFunction():\n    pass",
        )
        
        related = SymbolNode(
            symbol_id=2,
            name="CalledFunction",
            fully_qualified_name="Utils.CalledFunction",
            kind="FUNCTION",
            signature="def CalledFunction() -> str",
            documentation="Called function",
            file_path="utils.py",
            start_line=50,
            end_line=55,
            depth=1,
            relation_type="CALLS",
        )
        
        result = TraversalResult(
            root_symbol=root,
            related_symbols=[related],
            total_symbols=2,
            total_tokens=500,
            max_depth_reached=1,
            was_truncated=False,
            cycles_detected=0,
        )
        
        markdown = traverser.format_result_markdown(result, include_stats=True)
        
        assert "RootFunction" in markdown
        assert "CalledFunction" in markdown
        assert "2 symbols" in markdown
        assert "max depth 1" in markdown
        assert "CALLS" in markdown
        assert "```" in markdown  # Code block
        assert "def RootFunction():" in markdown
    
    @pytest.mark.asyncio
    async def test_symbol_not_found(self, traverser, mock_session):
        """Test handling of non-existent symbol."""
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_session.execute.return_value = mock_result
        
        config = TraversalConfig(depth=1)
        result = await traverser.traverse(symbol_id=999, config=config)
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_both_direction_traversal(self, traverser, mock_session, mock_symbol, mock_file):
        """Test bidirectional traversal."""
        call_count = [0]
        
        async def execute_side_effect(*args, **kwargs):
            call_count[0] += 1
            
            if call_count[0] == 1:
                # Get root
                mock_result = MagicMock()
                mock_result.first.return_value = (mock_symbol, mock_file)
                return mock_result
            elif call_count[0] == 2:
                # Get root code
                mock_result = MagicMock()
                mock_result.first.return_value = ("def test():\n    pass",)
                return mock_result
            elif call_count[0] == 3:
                # Downstream relations
                mock_result = MagicMock()
                mock_result.all.return_value = [(2, RelationTypeEnum.CALLS)]
                return mock_result
            elif call_count[0] == 4:
                # Upstream relations
                mock_result = MagicMock()
                mock_result.all.return_value = [(3, RelationTypeEnum.CALLS)]
                return mock_result
            else:
                # Return mock symbols
                symbol = MagicMock(spec=Symbol)
                symbol.id = call_count[0] - 2
                symbol.name = f"Function{symbol.id}"
                symbol.fully_qualified_name = f"Module.Function{symbol.id}"
                symbol.kind = SymbolKindEnum.FUNCTION
                symbol.signature = f"def Function{symbol.id}() -> None"
                symbol.documentation = ""
                symbol.start_line = 10
                symbol.end_line = 15
                symbol.access_modifier = AccessModifierEnum.PUBLIC
                symbol.return_type = "None"
                symbol.parameters = []
                symbol.complexity = 1
                
                mock_result = MagicMock()
                mock_result.first.return_value = (symbol, mock_file)
                return mock_result
        
        mock_session.execute.side_effect = execute_side_effect
        
        config = TraversalConfig(depth=1, direction=TraversalDirection.BOTH)
        result = await traverser.traverse(symbol_id=1, config=config)
        
        assert result is not None
        # Should have downstream and upstream symbols
        assert result.total_symbols >= 2


class TestTraversalDirection:
    """Test TraversalDirection enum."""
    
    def test_direction_values(self):
        """Test enum values."""
        assert TraversalDirection.DOWNSTREAM.value == "downstream"
        assert TraversalDirection.UPSTREAM.value == "upstream"
        assert TraversalDirection.BOTH.value == "both"
    
    def test_direction_from_string(self):
        """Test creating enum from string."""
        assert TraversalDirection("downstream") == TraversalDirection.DOWNSTREAM
        assert TraversalDirection("upstream") == TraversalDirection.UPSTREAM
        assert TraversalDirection("both") == TraversalDirection.BOTH


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

