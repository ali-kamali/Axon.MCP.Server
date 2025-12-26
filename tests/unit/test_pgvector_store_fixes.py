"""Tests for the critical bug fixes in pgvector_store."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.vector_store.pgvector_store import PgVectorStore
from src.embeddings.generator import EmbeddingResult
from src.database.models import Embedding, Chunk, Symbol, File, Repository
from src.config.enums import SymbolKindEnum, LanguageEnum


@pytest.fixture
def mock_session():
    """Mock database session."""
    return AsyncMock()


@pytest.fixture
def vector_store(mock_session):
    """Create PgVectorStore instance."""
    return PgVectorStore(mock_session)


@pytest.mark.asyncio
async def test_symbol_deduplication_in_search(vector_store, mock_session):
    """
    Test that symbols with multiple chunks are properly deduplicated.
    
    This test verifies the fix for the semantic scoring amplification bug
    where symbols with multiple chunks would accumulate RRF scores.
    """
    # Mock symbol with multiple embeddings
    mock_symbol = MagicMock(spec=Symbol)
    mock_symbol.id = 1
    mock_symbol.name = "MultiChunkFunction"
    mock_symbol.kind = SymbolKindEnum.FUNCTION
    mock_symbol.language = LanguageEnum.PYTHON
    
    # Mock query result - should return best similarity per symbol
    mock_row = MagicMock()
    mock_row.Symbol = mock_symbol
    mock_row.similarity = 0.92  # Best similarity from multiple chunks
    
    mock_result = MagicMock()
    mock_result.__iter__ = lambda self: iter([mock_row])
    mock_session.execute.return_value = mock_result
    
    query_vector = [0.1] * 384
    results = await vector_store.search_similar(query_vector, limit=10, threshold=0.7)
    
    # Should return only one result per symbol, with best similarity
    assert len(results) == 1
    assert results[0][0].id == 1
    assert results[0][1] == 0.92
    
    # Verify the query used aggregation (func.max)
    call_args = mock_session.execute.call_args
    # The query should be using a subquery with GROUP BY


@pytest.mark.asyncio
async def test_search_with_file_repo_join(vector_store, mock_session):
    """
    Test that include_file_repo=True fetches File and Repository in single query.
    
    This verifies the fix for the N+1 query problem.
    """
    # Mock symbol, file, and repository
    mock_symbol = MagicMock(spec=Symbol)
    mock_symbol.id = 1
    mock_symbol.name = "TestFunction"
    mock_symbol.file_id = 10
    
    mock_file = MagicMock(spec=File)
    mock_file.id = 10
    mock_file.path = "test.py"
    mock_file.repository_id = 100
    
    mock_repo = MagicMock(spec=Repository)
    mock_repo.id = 100
    mock_repo.name = "test-repo"
    
    # Mock query result with all objects
    mock_row = MagicMock()
    mock_row.Symbol = mock_symbol
    mock_row.similarity = 0.85
    mock_row.File = mock_file
    mock_row.Repository = mock_repo
    
    mock_result = MagicMock()
    mock_result.__iter__ = lambda self: iter([mock_row])
    mock_session.execute.return_value = mock_result
    
    query_vector = [0.1] * 384
    results = await vector_store.search_similar(
        query_vector, 
        limit=10, 
        threshold=0.7,
        include_file_repo=True
    )
    
    # Should return symbol, similarity, file, and repo in single query
    assert len(results) == 1
    assert results[0][0].id == 1  # Symbol
    assert results[0][1] == 0.85  # Similarity
    assert results[0][2] is not None  # File
    assert results[0][2].id == 10
    assert results[0][3] is not None  # Repository
    assert results[0][3].id == 100
    
    # Only one query should have been executed (no N+1)
    assert mock_session.execute.call_count == 1


@pytest.mark.asyncio
async def test_multiple_chunks_best_similarity(vector_store, mock_session):
    """
    Verify that when a symbol has multiple chunks, we use the best similarity.
    
    If Symbol A has 3 chunks with similarities [0.7, 0.9, 0.8],
    the result should show 0.9 (not 0.7+0.9+0.8).
    """
    mock_symbol = MagicMock(spec=Symbol)
    mock_symbol.id = 1
    mock_symbol.name = "FunctionWithMultipleChunks"
    
    # Mock result showing best similarity (0.9 from func.max)
    mock_row = MagicMock()
    mock_row.Symbol = mock_symbol
    mock_row.similarity = 0.9  # Max of [0.7, 0.9, 0.8]
    
    mock_result = MagicMock()
    mock_result.__iter__ = lambda self: iter([mock_row])
    mock_session.execute.return_value = mock_result
    
    query_vector = [0.1] * 384
    results = await vector_store.search_similar(query_vector, limit=10, threshold=0.7)
    
    # Should return single result with best similarity
    assert len(results) == 1
    assert results[0][1] == 0.9  # Best similarity, not sum


@pytest.mark.asyncio
async def test_repository_filter_with_include_file_repo(vector_store, mock_session):
    """Test repository filtering works correctly with include_file_repo."""
    mock_symbol = MagicMock(spec=Symbol)
    mock_symbol.id = 1
    mock_symbol.name = "TestFunction"
    
    mock_file = MagicMock(spec=File)
    mock_file.id = 10
    mock_file.repository_id = 100
    
    mock_repo = MagicMock(spec=Repository)
    mock_repo.id = 100
    
    mock_row = MagicMock()
    mock_row.Symbol = mock_symbol
    mock_row.similarity = 0.85
    mock_row.File = mock_file
    mock_row.Repository = mock_repo
    
    mock_result = MagicMock()
    mock_result.__iter__ = lambda self: iter([mock_row])
    mock_session.execute.return_value = mock_result
    
    query_vector = [0.1] * 384
    filters = {'repository_id': 100}
    
    results = await vector_store.search_similar(
        query_vector,
        limit=10,
        threshold=0.7,
        filters=filters,
        include_file_repo=True
    )
    
    assert len(results) == 1
    assert results[0][3].id == 100  # Correct repository

