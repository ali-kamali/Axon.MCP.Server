import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from src.utils.system_context_generator import SystemContextGenerator
from src.workers.system_context_worker import _generate_context_async
from src.mcp_server.tools.system_map import get_system_map

@pytest.mark.asyncio
async def test_system_context_generator():
    """Test the generator class."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_repo = MagicMock()
    mock_repo.id = 1
    mock_repo.name = "TestRepo"
    mock_repo.description = "Test Desc"
    mock_repo.primary_language = "Python"
    
    # Mock results
    repo_result = MagicMock()
    repo_result.scalars.return_value.all.return_value = [mock_repo]

    lang_result = MagicMock()
    lang_result.scalars.return_value.all.return_value = ["Python"]

    fw_result = MagicMock()
    fw_result.scalars.return_value.all.return_value = ["net8.0"]

    symbol_result = MagicMock()
    mock_symbol = MagicMock()
    mock_symbol.name = "TestClass"
    mock_symbol.kind = "class"
    mock_symbol.file.path = "test.py"
    mock_symbol.ai_enrichment = {"functional_summary": "Test Summary"}
    mock_symbol.documentation = "Docs"
    symbol_result.scalars.return_value.all.return_value = [mock_symbol]
    
    # Sequence: Repos, Languages, Frameworks, Symbols
    mock_session.execute.side_effect = [repo_result, lang_result, fw_result, symbol_result]
    
    generator = SystemContextGenerator(mock_session)
    context = await generator.generate_system_map(repository_id=1)
    
    assert "generated_at" in context
    assert len(context["repositories"]) == 1
    assert context["repositories"][0]["name"] == "TestRepo"
    # Ensure generated_at is an ISO format string (basic check)
    assert "T" in context["generated_at"]

@pytest.mark.asyncio
async def test_worker_caching():
    """Test that worker caches the result."""
    with patch("src.workers.system_context_worker.AsyncSessionLocal") as MockSession, \
         patch("src.workers.system_context_worker.get_cache") as mock_get_cache, \
         patch("src.workers.system_context_worker.get_distributed_lock") as mock_get_lock, \
         patch("src.workers.system_context_worker.SystemContextGenerator") as MockGen:
         
         # Mock Cache
         mock_cache_instance = AsyncMock()
         mock_get_cache.return_value = mock_cache_instance
         
         # Mock Lock
         mock_lock = MagicMock()
         mock_get_lock.return_value = mock_lock
         # Mock context manager for lock.acquire
         mock_lock_ctx = MagicMock()
         mock_lock_ctx.__enter__.return_value = True # acquired = True
         mock_lock.acquire.return_value = mock_lock_ctx

         # Mock Generator
         instance = MockGen.return_value
         instance.generate_system_map = AsyncMock(return_value={"test": "context", "generated_at": "now"})
         
         # Mock session
         mock_session = AsyncMock()
         mock_session.__aenter__.return_value = mock_session
         MockSession.return_value = mock_session

         await _generate_context_async(repository_id=None)
         
         mock_cache_instance.set.assert_called_once()
         call_args = mock_cache_instance.set.call_args
         assert call_args[0][0] == "system_context_map"  # Key
         assert call_args[0][1] == {"test": "context", "generated_at": "now"}   # Value

@pytest.mark.asyncio
async def test_mcp_tool_retrieval():
    """Test tool interaction with cache."""
    mock_ctx = MagicMock()
    
    # CASE 1: Cache Hit
    with patch("src.mcp_server.tools.system_map.get_cache") as mock_get_cache:
        mock_cache_instance = AsyncMock()
        mock_cache_instance.get.return_value = "{'cached': 'data'}"
        mock_get_cache.return_value = mock_cache_instance
        
        result = await get_system_map(mock_ctx)
        assert result == "{'cached': 'data'}"

    # CASE 2: Cache Miss (Trigger worker)
    with patch("src.mcp_server.tools.system_map.get_cache") as mock_get_cache, \
         patch("src.mcp_server.tools.system_map.generate_context") as mock_task:
        
        mock_cache_instance = AsyncMock()
        mock_cache_instance.get.return_value = None
        mock_get_cache.return_value = mock_cache_instance
        
        result = await get_system_map(mock_ctx)
        
        assert "System map is being generated" in result
        mock_task.delay.assert_called_once()
