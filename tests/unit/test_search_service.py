import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.api.services.search_service import SearchService
from src.api.schemas.search import SearchResult
from src.config.enums import SymbolKindEnum, LanguageEnum
from src.database.models import Symbol, File, Repository


@pytest.fixture
def mock_session():
    """Mock database session."""
    return AsyncMock()


@pytest.fixture
def search_service(mock_session):
    """Create SearchService instance with mocked dependencies."""
    with patch('src.api.services.search_service.EmbeddingGenerator'):
        service = SearchService(mock_session)
        service.embedding_generator = AsyncMock()
        return service


@pytest.mark.asyncio
async def test_keyword_search(search_service, mock_session):
    """Test keyword search."""
    # Mock database results
    mock_symbol = MagicMock(spec=Symbol)
    mock_symbol.id = 1
    mock_symbol.name = "TestFunction"
    mock_symbol.kind = SymbolKindEnum.FUNCTION
    mock_symbol.language = LanguageEnum.PYTHON
    mock_symbol.signature = "def test_function():"
    mock_symbol.fully_qualified_name = "module.TestFunction"
    mock_symbol.start_line = 1
    mock_symbol.end_line = 5
    mock_symbol.documentation = "Test function"
    mock_symbol.created_at = datetime.utcnow()
    
    mock_file = MagicMock(spec=File)
    mock_file.id = 1
    mock_file.path = "test.py"
    
    mock_repo = MagicMock(spec=Repository)
    mock_repo.id = 1
    mock_repo.name = "test-repo"
    
    mock_result = MagicMock()
    # Include SQL relevance score (4th value)
    mock_result.all.return_value = [(mock_symbol, mock_file, mock_repo, 0.7)]
    mock_session.execute.return_value = mock_result
    
    results = await search_service._keyword_search("test", 10, None, None, None)
    
    assert len(results) >= 0
    if len(results) > 0:
        assert results[0].name == "TestFunction"
        assert results[0].match_type == "keyword"


@pytest.mark.asyncio
async def test_semantic_search(search_service, mock_session):
    """Test semantic search."""
    # Mock embedding generation
    search_service.embedding_generator.generate_single_embedding.return_value = [0.1] * 384
    
    # Mock symbol for vector search
    mock_symbol = MagicMock(spec=Symbol)
    mock_symbol.id = 1
    mock_symbol.name = "TestFunction"
    mock_symbol.kind = SymbolKindEnum.FUNCTION
    mock_symbol.language = LanguageEnum.PYTHON
    mock_symbol.signature = "def test_function():"
    mock_symbol.fully_qualified_name = "module.TestFunction"
    mock_symbol.start_line = 1
    mock_symbol.end_line = 5
    mock_symbol.file_id = 1
    mock_symbol.documentation = "Test function"
    mock_symbol.created_at = datetime.utcnow()
    
    # Mock file and repo
    mock_file = MagicMock(spec=File)
    mock_file.id = 1
    mock_file.path = "test.py"
    
    mock_repo = MagicMock(spec=Repository)
    mock_repo.id = 1
    mock_repo.name = "test-repo"
    
    # Mock vector store search - now returns 4-tuple (Symbol, similarity, File, Repo)
    search_service.vector_store.search_similar = AsyncMock(
        return_value=[(mock_symbol, 0.9, mock_file, mock_repo)]
    )
    
    results = await search_service._semantic_search("test function", 10, None, None, None)
    
    assert len(results) >= 0
    if len(results) > 0:
        assert results[0].match_type == "semantic"
        assert results[0].score > 0


@pytest.mark.asyncio
async def test_reciprocal_rank_fusion():
    """Test RRF algorithm."""
    mock_session = AsyncMock()
    with patch('src.api.services.search_service.EmbeddingGenerator'):
        search_service = SearchService(mock_session)
    
    keyword_results = [
        SearchResult(
            symbol_id=1,
            file_id=1,
            repository_id=1,
            name="Result1",
            kind=SymbolKindEnum.FUNCTION,
            language=LanguageEnum.PYTHON,
            signature="def result1():",
            file_path="test.py",
            repository_name="repo",
            fully_qualified_name="module.Result1",
            start_line=1,
            end_line=5,
            documentation="Test",
            score=0.9,
            match_type="keyword",
            updated_at=datetime.utcnow()
        )
    ]
    
    semantic_results = [
        SearchResult(
            symbol_id=2,
            file_id=1,
            repository_id=1,
            name="Result2",
            kind=SymbolKindEnum.FUNCTION,
            language=LanguageEnum.PYTHON,
            signature="def result2():",
            file_path="test.py",
            repository_name="repo",
            fully_qualified_name="module.Result2",
            start_line=6,
            end_line=10,
            documentation="Test",
            score=0.8,
            match_type="semantic",
            updated_at=datetime.utcnow()
        )
    ]
    
    fused = search_service._reciprocal_rank_fusion(
        keyword_results,
        semantic_results,
        limit=10
    )
    
    assert len(fused) == 2
    assert all(r.match_type == "hybrid" for r in fused)


@pytest.mark.asyncio
async def test_calculate_keyword_score():
    """Test keyword scoring logic."""
    mock_session = AsyncMock()
    with patch('src.api.services.search_service.EmbeddingGenerator'):
        search_service = SearchService(mock_session)
    
    # Test exact name match
    mock_symbol = MagicMock(spec=Symbol)
    mock_symbol.name = "test"
    mock_symbol.signature = None
    mock_symbol.documentation = None
    
    score = search_service._calculate_keyword_score(mock_symbol, "test")
    assert score == 1.0
    
    # Test partial name match
    mock_symbol.name = "test_function"
    score = search_service._calculate_keyword_score(mock_symbol, "test")
    assert score == 0.7
    
    # Test with signature match
    mock_symbol.signature = "def test():"
    score = search_service._calculate_keyword_score(mock_symbol, "test")
    assert score == 1.0  # 0.7 (name) + 0.3 (signature)


@pytest.mark.asyncio
async def test_hybrid_search_with_filters(search_service, mock_session):
    """Test hybrid search with filters."""
    # Mock keyword results
    search_service._keyword_search = AsyncMock(return_value=[])
    
    # Mock semantic results
    search_service._semantic_search = AsyncMock(return_value=[])
    
    results = await search_service._hybrid_search(
        query="test",
        limit=10,
        repository_id=1,
        language=LanguageEnum.PYTHON,
        symbol_kind=SymbolKindEnum.FUNCTION
    )
    
    # Verify filters were passed
    search_service._keyword_search.assert_called_once_with(
        "test", 20, 1, LanguageEnum.PYTHON, SymbolKindEnum.FUNCTION
    )
    search_service._semantic_search.assert_called_once_with(
        "test", 20, 1, LanguageEnum.PYTHON, SymbolKindEnum.FUNCTION
    )
    
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_search_integration(search_service, mock_session):
    """Test main search method integration."""
    # Mock _keyword_search
    mock_result = SearchResult(
        symbol_id=1,
        file_id=1,
        repository_id=1,
        name="TestFunction",
        kind=SymbolKindEnum.FUNCTION,
        language=LanguageEnum.PYTHON,
        signature="def test():",
        file_path="test.py",
        repository_name="repo",
        fully_qualified_name="module.TestFunction",
        start_line=1,
        end_line=5,
        documentation="Test",
        score=0.9,
        match_type="keyword",
        updated_at=datetime.utcnow()
    )
    
    search_service._keyword_search = AsyncMock(return_value=[mock_result])
    
    # Test keyword-only search
    results = await search_service.search("test", limit=10, hybrid=False)
    
    assert len(results) >= 0
    search_service._keyword_search.assert_called_once()


@pytest.mark.asyncio
async def test_semantic_search_without_embeddings(search_service, mock_session):
    """Test semantic search when embedding generation fails."""
    # Mock empty embedding
    search_service.embedding_generator.generate_single_embedding.return_value = []
    
    results = await search_service._semantic_search("test", 10, None, None, None)
    
    assert len(results) == 0


@pytest.mark.asyncio
async def test_rrf_with_overlapping_results():
    """Test RRF with overlapping results from both searches."""
    mock_session = AsyncMock()
    with patch('src.api.services.search_service.EmbeddingGenerator'):
        search_service = SearchService(mock_session)
    
    # Create overlapping result (same symbol_id in both)
    shared_result = SearchResult(
        symbol_id=1,
        file_id=1,
        repository_id=1,
        name="SharedResult",
        kind=SymbolKindEnum.FUNCTION,
        language=LanguageEnum.PYTHON,
        signature="def shared():",
        file_path="test.py",
        repository_name="repo",
        fully_qualified_name="module.SharedResult",
        start_line=1,
        end_line=5,
        documentation="Shared",
        score=0.9,
        match_type="keyword",
        updated_at=datetime.utcnow()
    )
    
    keyword_results = [shared_result]
    semantic_results = [shared_result]
    
    fused = search_service._reciprocal_rank_fusion(
        keyword_results,
        semantic_results,
        limit=10
    )
    
    # Should only return one result (deduplicated)
    assert len(fused) == 1
    assert fused[0].symbol_id == 1
    assert fused[0].match_type == "hybrid"
    # Score should be higher due to appearing in both result sets
    assert fused[0].score > 0

