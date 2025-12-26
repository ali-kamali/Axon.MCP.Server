
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.extractors.api_extractor import ApiEndpointExtractor
from src.database.models import Symbol, File
from src.config.enums import SymbolKindEnum, LanguageEnum

@pytest.mark.asyncio
async def test_extract_endpoints_includes_minimal_apis():
    # Mock Session
    session = AsyncMock()
    
    # Mock result for Controller Classes (empty)
    class_result = MagicMock()
    class_result.all.return_value = []
    
    # Mock result for Minimal API Endpoints
    endpoint_symbol = Symbol(
        id=1,
        name="GET /api/minimal",
        kind=SymbolKindEnum.ENDPOINT,
        start_line=10,
        structured_docs={
            'method': 'GET',
            'path': '/api/minimal',
            'type': 'minimal_api'
        }
    )
    file = File(
        id=1,
        path="Program.cs",
        language=LanguageEnum.CSHARP,
        repository_id=1
    )
    
    endpoint_result = MagicMock()
    endpoint_result.all.return_value = [(endpoint_symbol, file)]
    
    # Configure session.execute side effects
    # First call is for classes, second is for endpoints
    session.execute.side_effect = [class_result, endpoint_result]
    
    extractor = ApiEndpointExtractor(session)
    endpoints = await extractor.extract_endpoints(repository_id=1)
    
    assert len(endpoints) == 1
    ep = endpoints[0]
    assert ep.http_method == "GET"
    assert ep.route == "/api/minimal"
    assert ep.controller == "minimal_api"
    assert ep.file_path == "Program.cs"

@pytest.mark.asyncio
async def test_extract_endpoints_fallback_parsing():
    # Test fallback when structured_docs is missing
    session = AsyncMock()
    
    class_result = MagicMock()
    class_result.all.return_value = []
    
    endpoint_symbol = Symbol(
        id=1,
        name="POST /api/fallback",
        kind=SymbolKindEnum.ENDPOINT,
        start_line=20,
        structured_docs=None
    )
    file = File(
        id=1,
        path="Program.cs",
        language=LanguageEnum.CSHARP,
        repository_id=1
    )
    
    endpoint_result = MagicMock()
    endpoint_result.all.return_value = [(endpoint_symbol, file)]
    
    session.execute.side_effect = [class_result, endpoint_result]
    
    extractor = ApiEndpointExtractor(session)
    endpoints = await extractor.extract_endpoints(repository_id=1)
    
    assert len(endpoints) == 1
    ep = endpoints[0]
    assert ep.http_method == "POST"
    assert ep.route == "/api/fallback"
    assert ep.controller == "MinimalApi" # Default
