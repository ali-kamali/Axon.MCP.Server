import pytest
from unittest.mock import AsyncMock, Mock, MagicMock
from src.extractors.knowledge_extractor import KnowledgeExtractor, ExtractionResult
from src.parsers.base_parser import ParseResult, ParsedSymbol
from src.config.enums import LanguageEnum, SymbolKindEnum, AccessModifierEnum
from src.database.models import Symbol

@pytest.fixture
def mock_session():
    """Mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.add = Mock()
    return session

@pytest.fixture
def sample_parse_result():
    """Create sample parse result."""
    symbol = ParsedSymbol(
        kind=SymbolKindEnum.CLASS,
        name="TestClass",
        start_line=1,
        end_line=10,
        start_column=0,
        end_column=0,
        signature="public class TestClass",
        fully_qualified_name="Namespace.TestClass"
    )
    
    return ParseResult(
        language=LanguageEnum.CSHARP,
        file_path="test.cs",
        symbols=[symbol],
        imports=[],
        exports=[],
        parse_errors=[],
        parse_duration_ms=100.0
    )

@pytest.fixture
def sample_parse_result_with_method():
    """Create sample parse result with class and method."""
    class_symbol = ParsedSymbol(
        kind=SymbolKindEnum.CLASS,
        name="TestClass",
        start_line=1,
        end_line=10,
        start_column=0,
        end_column=0,
        signature="public class TestClass",
        fully_qualified_name="Namespace.TestClass"
    )
    
    method_symbol = ParsedSymbol(
        kind=SymbolKindEnum.METHOD,
        name="TestMethod",
        start_line=3,
        end_line=8,
        start_column=4,
        end_column=4,
        signature="public void TestMethod(string arg1, int arg2)",
        documentation="This is a test method",
        fully_qualified_name="Namespace.TestClass.TestMethod",
        parent_name="Namespace.TestClass",
        access_modifier=AccessModifierEnum.PUBLIC,
        parameters=[
            {"name": "arg1", "type": "string"},
            {"name": "arg2", "type": "int"}
        ],
        return_type="void"
    )
    
    return ParseResult(
        language=LanguageEnum.CSHARP,
        file_path="test.cs",
        symbols=[class_symbol, method_symbol],
        imports=[],
        exports=[],
        parse_errors=[],
        parse_duration_ms=100.0
    )

@pytest.mark.asyncio
async def test_extract_and_persist_basic(mock_session, sample_parse_result):
    """Test basic knowledge extraction."""
    extractor = KnowledgeExtractor(mock_session)
    
    result = await extractor.extract_and_persist(
        sample_parse_result,
        file_id=1,
        commit_id=1
    )
    
    assert result.symbols_created == 1
    assert result.chunks_created == 1
    assert len(result.errors) == 0
    mock_session.commit.assert_called()

@pytest.mark.asyncio
async def test_extract_and_persist_with_relationships(mock_session, sample_parse_result_with_method):
    """Test extraction with parent-child relationships."""
    extractor = KnowledgeExtractor(mock_session)
    
    result = await extractor.extract_and_persist(
        sample_parse_result_with_method,
        file_id=1,
        commit_id=1
    )
    
    assert result.symbols_created == 2
    assert result.relations_created == 1  # Parent-child relationship
    assert result.chunks_created >= 1
    assert len(result.errors) == 0
    mock_session.commit.assert_called()

@pytest.mark.asyncio
async def test_create_chunk():
    """Test chunk creation."""
    mock_session = AsyncMock()
    extractor = KnowledgeExtractor(mock_session)
    
    symbol = Symbol(
        id=1,
        file_id=1,
        language=LanguageEnum.CSHARP,
        kind=SymbolKindEnum.METHOD,
        name="TestMethod",
        fully_qualified_name="TestClass.TestMethod",
        start_line=1,
        end_line=5,
        start_column=0,
        end_column=0
    )
    
    parsed = ParsedSymbol(
        kind=SymbolKindEnum.METHOD,
        name="TestMethod",
        start_line=1,
        end_line=5,
        start_column=0,
        end_column=0,
        signature="public void TestMethod()",
        documentation="Test method documentation"
    )
    
    chunk = await extractor._create_chunk(symbol, parsed, file_id=1)
    
    assert chunk is not None
    assert "TestMethod" in chunk.content
    assert "Test method documentation" in chunk.content
    assert chunk.content_type == "signature_with_docs"
    assert chunk.token_count > 0
    assert chunk.content_hash is not None

@pytest.mark.asyncio
async def test_create_chunk_no_content():
    """Test chunk creation with no documentation or signature."""
    mock_session = AsyncMock()
    extractor = KnowledgeExtractor(mock_session)
    
    symbol = Symbol(
        id=1,
        file_id=1,
        language=LanguageEnum.CSHARP,
        kind=SymbolKindEnum.VARIABLE,
        name="testVar",
        fully_qualified_name="testVar",
        start_line=1,
        end_line=1,
        start_column=0,
        end_column=0
    )
    
    parsed = ParsedSymbol(
        kind=SymbolKindEnum.VARIABLE,
        name="testVar",
        start_line=1,
        end_line=1,
        start_column=0,
        end_column=0
    )
    
    chunk = await extractor._create_chunk(symbol, parsed, file_id=1)
    
    assert chunk is None

def test_calculate_complexity_function():
    """Test complexity calculation for functions."""
    mock_session = AsyncMock()
    extractor = KnowledgeExtractor(mock_session)
    
    # Function with parameters
    parsed = ParsedSymbol(
        kind=SymbolKindEnum.FUNCTION,
        name="testFunc",
        start_line=1,
        end_line=5,
        start_column=0,
        end_column=0,
        signature="function testFunc(a, b, c)",
        parameters=[
            {"name": "a", "type": "string"},
            {"name": "b", "type": "int"},
            {"name": "c", "type": "bool"}
        ]
    )
    
    complexity = extractor._calculate_complexity(parsed)
    
    assert complexity == 4  # Base complexity 1 + 3 parameters

def test_calculate_complexity_class():
    """Test complexity calculation for classes."""
    mock_session = AsyncMock()
    extractor = KnowledgeExtractor(mock_session)
    
    parsed = ParsedSymbol(
        kind=SymbolKindEnum.CLASS,
        name="TestClass",
        start_line=1,
        end_line=10,
        start_column=0,
        end_column=0,
        signature="public class TestClass"
    )
    
    complexity = extractor._calculate_complexity(parsed)
    
    assert complexity == 0  # Classes have no complexity by default

@pytest.mark.asyncio
async def test_extraction_with_errors(mock_session):
    """Test extraction handles errors gracefully."""
    # Create a parse result with an invalid symbol that will cause an error
    mock_session.flush.side_effect = Exception("Database error")
    
    extractor = KnowledgeExtractor(mock_session)
    
    symbol = ParsedSymbol(
        kind=SymbolKindEnum.CLASS,
        name="TestClass",
        start_line=1,
        end_line=10,
        start_column=0,
        end_column=0,
        signature="public class TestClass",
        fully_qualified_name="Namespace.TestClass"
    )
    
    parse_result = ParseResult(
        language=LanguageEnum.CSHARP,
        file_path="test.cs",
        symbols=[symbol],
        imports=[],
        exports=[],
        parse_errors=[],
        parse_duration_ms=100.0
    )
    
    with pytest.raises(Exception):
        await extractor.extract_and_persist(
            parse_result,
            file_id=1,
            commit_id=1
        )
    
    mock_session.rollback.assert_called()

@pytest.mark.asyncio
async def test_create_symbol():
    """Test symbol creation from parsed symbol."""
    mock_session = AsyncMock()
    extractor = KnowledgeExtractor(mock_session)
    
    parsed = ParsedSymbol(
        kind=SymbolKindEnum.METHOD,
        name="TestMethod",
        start_line=5,
        end_line=10,
        start_column=4,
        end_column=4,
        signature="public async Task<string> TestMethod(int id, string name)",
        documentation="Test method that does something",
        fully_qualified_name="MyNamespace.MyClass.TestMethod",
        parent_name="MyNamespace.MyClass",
        access_modifier=AccessModifierEnum.PUBLIC,
        parameters=[
            {"name": "id", "type": "int"},
            {"name": "name", "type": "string"}
        ],
        return_type="Task<string>"
    )
    
    symbol = await extractor._create_symbol(
        parsed,
        file_id=1,
        commit_id=2,
        language=LanguageEnum.CSHARP
    )
    
    assert symbol.file_id == 1
    assert symbol.commit_id == 2
    assert symbol.language == LanguageEnum.CSHARP
    assert symbol.kind == SymbolKindEnum.METHOD
    assert symbol.access_modifier == AccessModifierEnum.PUBLIC
    assert symbol.name == "TestMethod"
    assert symbol.fully_qualified_name == "MyNamespace.MyClass.TestMethod"
    assert symbol.start_line == 5
    assert symbol.end_line == 10
    assert symbol.signature == parsed.signature
    assert symbol.documentation == parsed.documentation
    assert symbol.parameters == parsed.parameters
    assert symbol.return_type == "Task<string>"
    assert symbol.complexity > 0
    assert symbol.token_count > 0

