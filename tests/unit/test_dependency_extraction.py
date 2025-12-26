import pytest
from unittest.mock import AsyncMock, Mock
from src.extractors.knowledge_extractor import KnowledgeExtractor
from src.parsers.base_parser import ParseResult, ParsedSymbol
from src.config.enums import LanguageEnum, SymbolKindEnum
from src.database.models import File

@pytest.fixture
def mock_session():
    """Mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = Mock()
    return session

@pytest.mark.asyncio
async def test_extract_dependencies_npm(mock_session):
    """Test extracting NPM dependencies from package.json symbols."""
    extractor = KnowledgeExtractor(mock_session)
    
    # Mock file query result
    mock_result = Mock()
    mock_result.scalar_one_or_none.return_value = 1  # repository_id
    mock_session.execute.return_value = mock_result
    
    # Create parsed symbols representing npm dependencies
    symbols = [
        ParsedSymbol(
            kind=SymbolKindEnum.CONSTANT,
            name="react",
            start_line=0, end_line=0, start_column=0, end_column=0,
            signature="dependency: react@^18.0.0",
            structured_docs={
                'type': 'npm_package',
                'version': '^18.0.0',
                'is_dev_dependency': False
            }
        ),
        ParsedSymbol(
            kind=SymbolKindEnum.CONSTANT,
            name="typescript",
            start_line=0, end_line=0, start_column=0, end_column=0,
            signature="devDependency: typescript@^4.0.0",
            structured_docs={
                'type': 'npm_package',
                'version': '^4.0.0',
                'is_dev_dependency': True
            }
        )
    ]
    
    parse_result = ParseResult(
        language=LanguageEnum.JAVASCRIPT,
        file_path="package.json",
        symbols=symbols,
        imports=[], exports=[], parse_errors=[], parse_duration_ms=10
    )
    
    dependencies = await extractor._create_dependencies(parse_result, file_id=1)
    
    assert len(dependencies) == 2
    
    # Check react dependency
    react = next(d for d in dependencies if d.package_name == "react")
    assert react.package_version == "^18.0.0"
    assert react.dependency_type == "npm"
    assert react.is_dev_dependency == 0
    
    # Check typescript dependency
    ts = next(d for d in dependencies if d.package_name == "typescript")
    assert ts.package_version == "^4.0.0"
    assert ts.dependency_type == "npm"
    assert ts.is_dev_dependency == 1

@pytest.mark.asyncio
async def test_extract_dependencies_nuget(mock_session):
    """Test extracting NuGet dependencies from .csproj symbols."""
    extractor = KnowledgeExtractor(mock_session)
    
    # Mock file query result
    mock_result = Mock()
    mock_result.scalar_one_or_none.return_value = 1  # repository_id
    mock_session.execute.return_value = mock_result
    
    # Create parsed symbols representing nuget dependencies
    symbols = [
        ParsedSymbol(
            kind=SymbolKindEnum.CONSTANT,
            name="Newtonsoft.Json",
            start_line=0, end_line=0, start_column=0, end_column=0,
            signature="PackageReference: Newtonsoft.Json v13.0.1",
            structured_docs={
                'type': 'nuget_package',
                'version': '13.0.1',
                'is_dev_dependency': False
            }
        )
    ]
    
    parse_result = ParseResult(
        language=LanguageEnum.CSHARP,
        file_path="Project.csproj",
        symbols=symbols,
        imports=[], exports=[], parse_errors=[], parse_duration_ms=10
    )
    
    dependencies = await extractor._create_dependencies(parse_result, file_id=1)
    
    assert len(dependencies) == 1
    
    dep = dependencies[0]
    assert dep.package_name == "Newtonsoft.Json"
    assert dep.package_version == "13.0.1"
    assert dep.dependency_type == "nuget"
    assert dep.is_dev_dependency == 0
