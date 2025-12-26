
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from src.mcp_server.tools.symbols import find_usages, find_references
from src.config.enums import SymbolKindEnum, RelationTypeEnum
from mcp.types import TextContent

@pytest.fixture
def mock_session():
    session = AsyncMock()
    # Mock the context manager behavior
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    return session

@pytest.fixture
def mock_get_async_session(mock_session):
    @patch('src.mcp_server.tools.symbols.get_async_session')
    def _mock(mock_func):
        mock_func.return_value = mock_session
        return mock_func
    return _mock

@pytest.mark.asyncio
async def test_find_usages_empty_controller_suggestion(mock_session):
    """Verify suggestions for empty controller usages."""
    
    # Mock Symbol Lookup
    symbol_mock = Mock()
    symbol_mock.id = 1
    symbol_mock.name = "UsersController"
    symbol_mock.kind = SymbolKindEnum.CLASS
    symbol_mock.attributes = ["ApiController"]
    
    # Mock Session Execute for Symbol
    mock_result_symbol = Mock()
    mock_result_symbol.scalar_one_or_none.return_value = symbol_mock
    
    # Mock Session Execute for Usages (Empty)
    mock_result_usages = Mock()
    mock_result_usages.all.return_value = []
    
    mock_session.execute.side_effect = [mock_result_symbol, mock_result_usages]

    with patch('src.mcp_server.tools.symbols.get_async_session') as mock_get_session:
        mock_get_session.return_value.__aenter__.return_value = mock_session
        
        results = await find_usages(1)
        
        assert len(results) == 1
        text = results[0].text
        assert "No usages found" in text
        assert "This looks like an API Controller" in text
        assert "find_api_endpoints" in text

@pytest.mark.asyncio
async def test_find_usages_filtering(mock_session):
    """Verify relationship type filtering."""
    
    # Mock Symbol
    symbol_mock = Mock()
    symbol_mock.id = 2
    symbol_mock.name = "ProcessData"
    symbol_mock.kind = SymbolKindEnum.METHOD
    
    # Mock Usages
    usage1 = (Mock(relation_type=RelationTypeEnum.CALLS), Mock(name="Caller", kind=SymbolKindEnum.METHOD, start_line=10), Mock(path="test.cs"))
    
    mock_result_symbol = Mock()
    mock_result_symbol.scalar_one_or_none.return_value = symbol_mock
    
    mock_result_usages = Mock()
    mock_result_usages.all.return_value = [usage1]
    
    # We can't easily verify the SQL construction with mocks without inspecting the call args deeply
    # But we can verify it executes successfully and returns formatted result.
    mock_session.execute.side_effect = [mock_result_symbol, mock_result_usages]
    
    with patch('src.mcp_server.tools.symbols.get_async_session') as mock_get_session:
        mock_get_session.return_value.__aenter__.return_value = mock_session
        
        results = await find_usages(2, relationship_types=['CALLS'])
        
        text = results[0].text
        assert "Found 1 usages" in text
        assert "Caller" in text
        # Verify specific stats header is present
        assert "### CALLS (1)" in text

@pytest.mark.asyncio
async def test_find_usages_stats_grouping(mock_session):
    """Verify usage statistics validation."""
    
    # Mock Symbol
    symbol_mock = Mock()
    symbol_mock.id = 3
    symbol_mock.name = "MyService"
    symbol_mock.kind = SymbolKindEnum.CLASS
    
    # Mock Usages causing diverse stats
    u1 = (Mock(relation_type=RelationTypeEnum.CALLS), Mock(name="C1", kind=SymbolKindEnum.METHOD, start_line=1), Mock(path="1.cs"))
    u2 = (Mock(relation_type=RelationTypeEnum.CALLS), Mock(name="C2", kind=SymbolKindEnum.METHOD, start_line=2), Mock(path="2.cs"))
    u3 = (Mock(relation_type=RelationTypeEnum.USES), Mock(name="U1", kind=SymbolKindEnum.CLASS, start_line=3), Mock(path="3.cs"))
    
    mock_result_symbol = Mock()
    mock_result_symbol.scalar_one_or_none.return_value = symbol_mock
    
    mock_result_usages = Mock()
    mock_result_usages.all.return_value = [u1, u2, u3]
    
    mock_session.execute.side_effect = [mock_result_symbol, mock_result_usages]
    
    with patch('src.mcp_server.tools.symbols.get_async_session') as mock_get_session:
        mock_get_session.return_value.__aenter__.return_value = mock_session
        
        results = await find_usages(3)
        
        text = results[0].text
        assert "Found 3 usages" in text
        assert "### CALLS (2)" in text
        assert "### USES (1)" in text
        assert "C1" in text
        assert "C2" in text
        assert "U1" in text
