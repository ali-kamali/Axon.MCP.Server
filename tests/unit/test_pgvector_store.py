import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from datetime import datetime

from src.vector_store.pgvector_store import PgVectorStore
from src.embeddings.generator import EmbeddingResult
from src.database.models import Embedding, Chunk, Symbol
from src.config.enums import SymbolKindEnum, LanguageEnum


@pytest.fixture
def mock_session():
    """Mock database session."""
    session = AsyncMock()
    # AsyncSession APIs used by PgVectorStore
    session.execute = AsyncMock()
    session.flush = AsyncMock()

    # Synchronous AsyncSession methods should be plain Mocks,
    # otherwise AsyncMock emits "coroutine was never awaited" warnings.
    session.add = Mock()
    session.add_all = Mock()
    return session


@pytest.fixture
def vector_store(mock_session):
    """Create PgVectorStore instance."""
    return PgVectorStore(mock_session)


@pytest.mark.asyncio
async def test_store_embeddings_success(vector_store, mock_session):
    """Test storing embeddings successfully."""
    # Mock chunk - use simple MagicMock to avoid InvalidSpecError
    mock_chunk = MagicMock()
    mock_chunk.id = 1
    mock_chunk.symbol_id = 10
    
    # Mock for batch query (uses scalars() now)
    mock_chunks_result = MagicMock()
    mock_chunks_result.scalars.return_value = [mock_chunk]
    mock_session.execute.return_value = mock_chunks_result
    
    # Create embedding results
    embedding_results = [
        EmbeddingResult(
            chunk_id=1,
            vector=[0.1] * 384,
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_version="1.0",
            dimension=384
        )
    ]
    
    stored_count = await vector_store.store_embeddings(embedding_results)
    
    assert stored_count == 1
    # Implementation uses add_all and flush
    mock_session.add_all.assert_called_once()
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_store_embeddings_chunk_not_found(vector_store, mock_session):
    """Test storing embeddings when chunk is not found."""
    # UPDATED: Mock empty result for batch query
    mock_chunks_result = MagicMock()
    mock_chunks_result.scalars.return_value = []  # No chunks found
    mock_session.execute.return_value = mock_chunks_result
    
    embedding_results = [
        EmbeddingResult(
            chunk_id=999,
            vector=[0.1] * 384,
            model_name="test-model",
            model_version="1.0",
            dimension=384
        )
    ]
    
    stored_count = await vector_store.store_embeddings(embedding_results)
    
    assert stored_count == 0
    # UPDATED: add_all should not be called when no valid embeddings
    mock_session.add_all.assert_not_called()


@pytest.mark.asyncio
async def test_store_embeddings_error_handling(vector_store, mock_session):
    """Test error handling during embedding storage."""
    # With proper transaction management, exceptions are raised
    # Mock chunk lookup to raise an exception
    mock_session.execute.side_effect = Exception("Database error")
    
    embedding_results = [
        EmbeddingResult(
            chunk_id=1,
            vector=[0.1] * 384,
            model_name="test-model",
            model_version="1.0",
            dimension=384
        )
    ]
    
    # Expect exception to be raised (proper error handling)
    with pytest.raises(Exception) as exc_info:
        await vector_store.store_embeddings(embedding_results)
    
    assert "Database error" in str(exc_info.value)
    # Note: Implementation re-raises exception; session rollback is handled by caller/context manager


@pytest.mark.asyncio
async def test_search_similar_basic(vector_store, mock_session):
    """Test basic similarity search."""
    # Mock symbol - use simple MagicMock to avoid InvalidSpecError
    mock_symbol = MagicMock()
    mock_symbol.id = 1
    mock_symbol.name = "TestFunction"
    mock_symbol.kind = SymbolKindEnum.FUNCTION
    mock_symbol.language = LanguageEnum.PYTHON
    
    # Mock file and repository (required for the query)
    mock_file = MagicMock()
    mock_file.id = 10
    mock_file.path = "test.py"
    mock_file.repository_id = 100
    
    mock_repo = MagicMock()
    mock_repo.id = 100
    mock_repo.name = "test-repo"
    
    # Mock query result row - implementation uses .all() on result
    mock_row = MagicMock()
    mock_row.Symbol = mock_symbol
    mock_row.vector_score = 0.85
    mock_row.File = mock_file
    mock_row.Repository = mock_repo
    
    mock_result = MagicMock()
    mock_result.all.return_value = [mock_row]
    mock_session.execute.return_value = mock_result
    
    query_vector = [0.1] * 384
    results = await vector_store.search_similar(query_vector, limit=10, threshold=0.7)
    
    # Verify results - returns 4-tuple (Symbol, similarity, File?, Repo?)
    assert len(results) == 1
    assert results[0][0].id == 1
    # Score is boosted by +0.05 for FUNCTION kind
    assert results[0][1] >= 0.85
    assert results[0][2] is None  # No file when include_file_repo=False
    assert results[0][3] is None  # No repo when include_file_repo=False


@pytest.mark.asyncio
async def test_search_similar_with_language_filter(vector_store, mock_session):
    """Test similarity search with language filter."""
    mock_result = MagicMock()
    mock_result.all.return_value = []  # Use .all() instead of __iter__
    mock_session.execute.return_value = mock_result
    
    query_vector = [0.1] * 384
    filters = {'language': LanguageEnum.PYTHON}
    
    results = await vector_store.search_similar(
        query_vector, 
        limit=10, 
        threshold=0.7, 
        filters=filters
    )
    
    assert isinstance(results, list)
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_search_similar_with_repository_filter(vector_store, mock_session):
    """Test similarity search with repository filter."""
    mock_result = MagicMock()
    mock_result.all.return_value = []  # Use .all() instead of __iter__
    mock_session.execute.return_value = mock_result
    
    query_vector = [0.1] * 384
    filters = {'repository_id': 1}
    
    results = await vector_store.search_similar(
        query_vector, 
        limit=10, 
        threshold=0.7, 
        filters=filters
    )
    
    assert isinstance(results, list)
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_search_similar_with_symbol_kind_filter(vector_store, mock_session):
    """Test similarity search with symbol kind filter."""
    mock_result = MagicMock()
    mock_result.all.return_value = []  # Use .all() instead of __iter__
    mock_session.execute.return_value = mock_result
    
    query_vector = [0.1] * 384
    filters = {'symbol_kind': SymbolKindEnum.FUNCTION}
    
    results = await vector_store.search_similar(
        query_vector, 
        limit=10, 
        threshold=0.7, 
        filters=filters
    )
    
    assert isinstance(results, list)
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_search_similar_with_multiple_filters(vector_store, mock_session):
    """Test similarity search with multiple filters."""
    mock_result = MagicMock()
    mock_result.all.return_value = []  # Use .all() instead of __iter__
    mock_session.execute.return_value = mock_result
    
    query_vector = [0.1] * 384
    filters = {
        'language': LanguageEnum.PYTHON,
        'repository_id': 1,
        'symbol_kind': SymbolKindEnum.FUNCTION
    }
    
    results = await vector_store.search_similar(
        query_vector, 
        limit=10, 
        threshold=0.7, 
        filters=filters
    )
    
    assert isinstance(results, list)
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_create_vector_index_ivfflat(vector_store, mock_session):
    """Test creating IVFFlat vector index."""
    await vector_store.create_vector_index(index_type="ivfflat", lists=100)
    
    # Should execute 3 statements: DROP, CREATE, and ANALYZE
    # ANALYZE is required for Postgres to use the IVFFlat index
    assert mock_session.execute.call_count == 3
    # Implementation uses flush instead of commit
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_create_vector_index_hnsw(vector_store, mock_session):
    """Test creating HNSW vector index."""
    await vector_store.create_vector_index(index_type="hnsw")
    
    # Should execute 2 statements: DROP and CREATE
    assert mock_session.execute.call_count == 2
    # Implementation uses flush instead of commit
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_create_vector_index_error(vector_store, mock_session):
    """Test error handling during index creation."""
    mock_session.execute.side_effect = Exception("Index creation failed")
    
    with pytest.raises(Exception) as exc_info:
        await vector_store.create_vector_index(index_type="ivfflat")
    
    assert "Index creation failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_store_multiple_embeddings(vector_store, mock_session):
    """Test storing multiple embeddings in batch."""
    # Mock chunks - use simple MagicMock to avoid InvalidSpecError
    mock_chunks = []
    for i in range(3):
        mock_chunk = MagicMock()
        mock_chunk.id = i + 1
        mock_chunk.symbol_id = (i + 1) * 10
        mock_chunks.append(mock_chunk)
    
    # Mock batch query with all chunks
    mock_chunks_result = MagicMock()
    mock_chunks_result.scalars.return_value = mock_chunks
    mock_session.execute.return_value = mock_chunks_result
    
    embedding_results = [
        EmbeddingResult(
            chunk_id=i + 1,
            vector=[0.1 * (i + 1)] * 384,
            model_name="test-model",
            model_version="1.0",
            dimension=384
        )
        for i in range(3)
    ]
    
    stored_count = await vector_store.store_embeddings(embedding_results)
    
    assert stored_count == 3
    # Implementation uses add_all with all embeddings at once
    mock_session.add_all.assert_called_once()
    # Verify add_all was called with 3 embeddings
    call_args = mock_session.add_all.call_args[0][0]
    assert len(call_args) == 3
    mock_session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_search_similar_empty_results(vector_store, mock_session):
    """Test similarity search with no results."""
    mock_result = MagicMock()
    mock_result.all.return_value = []  # Use .all() instead of __iter__
    mock_session.execute.return_value = mock_result
    
    query_vector = [0.1] * 384
    results = await vector_store.search_similar(query_vector, limit=10, threshold=0.9)
    
    assert len(results) == 0

