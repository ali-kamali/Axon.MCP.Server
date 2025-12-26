import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.embeddings.generator import EmbeddingGenerator, EmbeddingResult, OPENAI_AVAILABLE


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.data = [
        MagicMock(embedding=[0.1] * 1536)
    ]
    mock_client.embeddings.create.return_value = mock_response
    return mock_client


@pytest.mark.skipif(not OPENAI_AVAILABLE, reason="OpenAI not installed")
@pytest.mark.asyncio
async def test_generate_openai_embeddings(mock_openai_client):
    """Test OpenAI embedding generation."""
    with patch('src.embeddings.generator.AsyncOpenAI', return_value=mock_openai_client):
        with patch('src.embeddings.generator.settings') as mock_settings:
            with patch('src.embeddings.generator.OPENAI_AVAILABLE', True):
                mock_settings.embedding_provider = "openai"
                mock_settings.openai_api_key = "test-key"
                mock_settings.openai_embedding_model = "text-embedding-3-small"
                mock_settings.openai_embedding_dimension = 1536
                mock_settings.embedding_batch_size = 100
                
                generator = EmbeddingGenerator()
                
                chunks = [
                    {'id': 1, 'content': 'Test content'}
                ]
                
                results = await generator.generate_embeddings(chunks)
                
                assert len(results) == 1
                assert results[0].chunk_id == 1
                assert len(results[0].vector) == 1536


@pytest.mark.asyncio
async def test_generate_local_embeddings():
    """Test local embedding generation."""
    with patch('src.embeddings.generator.settings') as mock_settings:
        mock_settings.embedding_provider = "local"
        mock_settings.local_embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
        mock_settings.embedding_batch_size = 100
        
        with patch('src.embeddings.generator.SentenceTransformer') as mock_st:
            import numpy as np
            mock_model = MagicMock()
            mock_model.encode.return_value = np.array([[0.1] * 384])
            mock_model.get_sentence_embedding_dimension.return_value = 384
            mock_st.return_value = mock_model
            
            generator = EmbeddingGenerator()
            
            chunks = [
                {'id': 1, 'content': 'Test content'}
            ]
            
            results = await generator.generate_embeddings(chunks)
            
            assert len(results) == 1
            assert results[0].chunk_id == 1


@pytest.mark.asyncio
async def test_generate_single_embedding():
    """Test single embedding generation."""
    with patch('src.embeddings.generator.settings') as mock_settings:
        mock_settings.embedding_provider = "local"
        mock_settings.local_embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
        mock_settings.embedding_batch_size = 100
        
        with patch('src.embeddings.generator.SentenceTransformer') as mock_st:
            import numpy as np
            mock_model = MagicMock()
            mock_model.encode.return_value = np.array([[0.1] * 384])
            mock_model.get_sentence_embedding_dimension.return_value = 384
            mock_st.return_value = mock_model
            
            generator = EmbeddingGenerator()
            
            vector = await generator.generate_single_embedding("Test text")
            
            assert len(vector) == 384


@pytest.mark.asyncio
async def test_batch_processing():
    """Test batch processing of multiple chunks."""
    with patch('src.embeddings.generator.settings') as mock_settings:
        mock_settings.embedding_provider = "local"
        mock_settings.local_embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
        mock_settings.embedding_batch_size = 2  # Small batch size for testing
        
        with patch('src.embeddings.generator.SentenceTransformer') as mock_st:
            import numpy as np
            mock_model = MagicMock()
            # Return different batches
            mock_model.encode.side_effect = [
                np.array([[0.1] * 384, [0.2] * 384]),
                np.array([[0.3] * 384])
            ]
            mock_model.get_sentence_embedding_dimension.return_value = 384
            mock_st.return_value = mock_model
            
            generator = EmbeddingGenerator()
            
            chunks = [
                {'id': 1, 'content': 'Test content 1'},
                {'id': 2, 'content': 'Test content 2'},
                {'id': 3, 'content': 'Test content 3'}
            ]
            
            results = await generator.generate_embeddings(chunks)
            
            assert len(results) == 3
            assert results[0].chunk_id == 1
            assert results[1].chunk_id == 2
            assert results[2].chunk_id == 3


@pytest.mark.asyncio
async def test_embedding_error_handling():
    """Test error handling during embedding generation."""
    with patch('src.embeddings.generator.settings') as mock_settings:
        mock_settings.embedding_provider = "local"
        mock_settings.local_embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
        mock_settings.embedding_batch_size = 2
        
        with patch('src.embeddings.generator.SentenceTransformer') as mock_st:
            import numpy as np
            mock_model = MagicMock()
            # First batch fails, second succeeds
            mock_model.encode.side_effect = [
                Exception("Encoding failed"),
                np.array([[0.3] * 384])
            ]
            mock_model.get_sentence_embedding_dimension.return_value = 384
            mock_st.return_value = mock_model
            
            generator = EmbeddingGenerator()
            
            chunks = [
                {'id': 1, 'content': 'Test content 1'},
                {'id': 2, 'content': 'Test content 2'},
                {'id': 3, 'content': 'Test content 3'}
            ]
            
            results = await generator.generate_embeddings(chunks)
            
            # Should only get results from successful batch
            assert len(results) == 1
            assert results[0].chunk_id == 3

