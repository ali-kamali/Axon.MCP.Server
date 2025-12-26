import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import select
from src.extractors.relationship_builder import RelationshipBuilder
from src.database.models import Symbol, Relation, File
from src.config.enums import SymbolKindEnum, RelationTypeEnum, LanguageEnum

@pytest.fixture
def mock_session():
    """Mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    return session

def test_extract_base_classes_csharp():
    """Test extracting base classes from C# signature."""
    session = AsyncMock()
    builder = RelationshipBuilder(session)
    
    # Test single inheritance
    signature1 = "public class Derived : Base"
    result1 = builder._extract_base_classes(signature1)
    assert result1 == ["Base"]
    
    # Test multiple interfaces
    signature2 = "public class MyClass : BaseClass, IInterface1, IInterface2"
    result2 = builder._extract_base_classes(signature2)
    assert "BaseClass" in result2
    assert "IInterface1" in result2
    assert "IInterface2" in result2
    
    # Test with braces
    signature3 = "public class Derived : Base {"
    result3 = builder._extract_base_classes(signature3)
    assert result3 == ["Base"]

def test_extract_base_classes_javascript():
    """Test extracting base classes from JavaScript/TypeScript signature."""
    session = AsyncMock()
    builder = RelationshipBuilder(session)
    
    # Test extends
    signature1 = "class Derived extends Base"
    result1 = builder._extract_base_classes(signature1)
    assert result1 == ["Base"]
    
    # Test extends with implements
    signature2 = "class MyClass extends Base implements IInterface"
    result2 = builder._extract_base_classes(signature2)
    assert "Base" in result2
    assert "IInterface" in result2

def test_extract_base_classes_typescript_implements():
    """Test extracting interfaces from TypeScript implements."""
    session = AsyncMock()
    builder = RelationshipBuilder(session)
    
    signature = "class MyClass implements IInterface1, IInterface2 {"
    result = builder._extract_base_classes(signature)
    assert "IInterface1" in result
    assert "IInterface2" in result

def test_extract_base_classes_no_inheritance():
    """Test extracting base classes when there's no inheritance."""
    session = AsyncMock()
    builder = RelationshipBuilder(session)
    
    signature = "public class SimpleClass {"
    result = builder._extract_base_classes(signature)
    assert result == []

@pytest.mark.asyncio
async def test_build_cross_file_relationships(mock_session):
    """Test building cross-file relationships."""
    # Create mock symbols
    base_class = Symbol(
        id=1,
        file_id=1,
        language=LanguageEnum.CSHARP,
        kind=SymbolKindEnum.CLASS,
        name="BaseClass",
        fully_qualified_name="MyNamespace.BaseClass",
        signature="public class BaseClass",
        start_line=1,
        end_line=10,
        start_column=0,
        end_column=0
    )
    
    derived_class = Symbol(
        id=2,
        file_id=2,
        language=LanguageEnum.CSHARP,
        kind=SymbolKindEnum.CLASS,
        name="DerivedClass",
        fully_qualified_name="MyNamespace.DerivedClass",
        signature="public class DerivedClass : BaseClass",
        start_line=1,
        end_line=15,
        start_column=0,
        end_column=0
    )
    
    interface_symbol = Symbol(
        id=3,
        file_id=3,
        language=LanguageEnum.CSHARP,
        kind=SymbolKindEnum.INTERFACE,
        name="IMyInterface",
        fully_qualified_name="MyNamespace.IMyInterface",
        signature="public interface IMyInterface",
        start_line=1,
        end_line=5,
        start_column=0,
        end_column=0
    )
    
    impl_class = Symbol(
        id=4,
        file_id=4,
        language=LanguageEnum.CSHARP,
        kind=SymbolKindEnum.CLASS,
        name="ImplClass",
        fully_qualified_name="MyNamespace.ImplClass",
        signature="public class ImplClass : IMyInterface",
        start_line=1,
        end_line=20,
        start_column=0,
        end_column=0
    )
    
    # Mock execute to return symbols
    mock_result = AsyncMock()
    mock_result.scalars().all.return_value = [base_class, derived_class, interface_symbol, impl_class]
    mock_session.execute.return_value = mock_result
    
    # Build relationships
    builder = RelationshipBuilder(mock_session)
    count = await builder.build_cross_file_relationships(repository_id=1)
    
    # Verify relationships were created
    assert count == 2  # DerivedClass -> BaseClass, ImplClass -> IMyInterface
    assert mock_session.commit.called

@pytest.mark.asyncio
async def test_build_import_relationships(mock_session):
    """Test building import relationships."""
    # Create mock files and symbols
    file1 = File(id=1, repository_id=1, path="file1.js", language=LanguageEnum.JAVASCRIPT, size_bytes=100)
    file2 = File(id=2, repository_id=1, path="file2.js", language=LanguageEnum.JAVASCRIPT, size_bytes=200)
    
    symbol1 = Symbol(
        id=1,
        file_id=1,
        language=LanguageEnum.JAVASCRIPT,
        kind=SymbolKindEnum.FUNCTION,
        name="function1",
        fully_qualified_name="file1.function1",
        signature="function function1()",
        start_line=1,
        end_line=5,
        start_column=0,
        end_column=0
    )
    
    symbol2 = Symbol(
        id=2,
        file_id=2,
        language=LanguageEnum.JAVASCRIPT,
        kind=SymbolKindEnum.FUNCTION,
        name="function2",
        fully_qualified_name="file2.function2",
        signature="function function2()",
        start_line=1,
        end_line=5,
        start_column=0,
        end_column=0
    )
    
    # Mock file query
    file_result = AsyncMock()
    file_result.scalars().all.return_value = [file1, file2]
    
    # Mock symbol queries
    symbol_result1 = AsyncMock()
    symbol_result1.scalars.return_value = [symbol1]
    
    symbol_result2 = AsyncMock()
    symbol_result2.scalars.return_value = [symbol2]
    
    # Setup execute mock to return different results based on query
    mock_session.execute.side_effect = [file_result, symbol_result1, symbol_result2]
    
    # Build import relationships
    builder = RelationshipBuilder(mock_session)
    imports_map = {1: ["file2.js"]}
    count = await builder.build_import_relationships(repository_id=1, imports_map=imports_map)
    
    # Verify
    assert count >= 0
    assert mock_session.commit.called

@pytest.mark.asyncio
async def test_build_cross_file_relationships_no_symbols(mock_session):
    """Test building relationships when there are no symbols."""
    # Mock empty result
    mock_result = AsyncMock()
    mock_result.scalars().all.return_value = []
    mock_session.execute.return_value = mock_result
    
    builder = RelationshipBuilder(mock_session)
    count = await builder.build_cross_file_relationships(repository_id=1)
    
    assert count == 0
    assert mock_session.commit.called

