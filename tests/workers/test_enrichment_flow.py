import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.workers.enrichment_worker import enrich_batch, _enrich_batch_async, MAX_ENRICHMENT_ITERATIONS, ENRICHMENT_BATCH_SIZE
from src.api.routes.enrichment import trigger_enrichment

@pytest.mark.asyncio
async def test_enrichment_flow():
    # Test task triggering via API
    mock_db = AsyncMock()
    mock_repo = MagicMock()
    mock_db.get.return_value = mock_repo
    
    with patch("src.api.routes.enrichment.enrich_batch") as mock_task:
        mock_task.delay.return_value.id = "test-task-id"
        
        response = await trigger_enrichment(repository_id=1, force=False, db=mock_db)
        
        assert response["status"] == "triggered"
        assert response["task_id"] == "test-task-id"
        mock_task.delay.assert_called_once_with(1)

@pytest.mark.asyncio
async def test_enrichment_worker_logic():
    # Test worker logic
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    
    mock_result = MagicMock()
    mock_symbol = MagicMock()
    mock_symbol.name = "TestSymbol"
    mock_symbol.file.path = "test.py"
    mock_symbol.kind = "class"
    mock_symbol.signature = "class TestSymbol"
    mock_symbol.documentation = "Docs"
    mock_symbol.ai_enrichment = None
    
    # Mock scalars().all()
    mock_result.scalars.return_value.all.return_value = [mock_symbol]
    mock_session.execute.return_value = mock_result
    
    with patch("src.workers.enrichment_worker.AsyncSessionLocal", return_value=mock_session), \
         patch("src.workers.enrichment_worker.LLMSummarizer") as MockLLM:
        
        mock_llm_instance = MockLLM.return_value
        # Valid JSON response
        mock_llm_instance.summarize_async = AsyncMock(return_value='{"business_purpose": "Valid Purpose", "functional_summary": "This is a valid summary with enough length."}')
        
        task = MagicMock()
        result = await _enrich_batch_async(task, repository_id=1)
        
        assert result["enriched"] == 1
        assert mock_symbol.ai_enrichment["business_purpose"] == "Valid Purpose"
        mock_session.commit.assert_called_once()  # Per-symbol commit

@pytest.mark.asyncio
async def test_enrichment_orphan_handling():
    """Test that orphaned symbols (no file) are skipped."""
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    
    mock_symbol = MagicMock()
    mock_symbol.name = "TestSymbol"
    mock_symbol.file = None # ORPHAN
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_symbol]
    mock_session.execute.return_value = mock_result
    
    with patch("src.workers.enrichment_worker.AsyncSessionLocal", return_value=mock_session), \
         patch("src.workers.enrichment_worker.LLMSummarizer") as MockLLM:
        
        task = MagicMock()
        result = await _enrich_batch_async(task, repository_id=1)
        
        assert result["enriched"] == 0
        assert result["failed"] == 1
        mock_session.commit.assert_not_called()

@pytest.mark.asyncio
async def test_recursion_limit():
    """Test that recursion stops after MAX_ITERATIONS."""
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    
    # Create batch of symbols
    symbols = []
    for _ in range(ENRICHMENT_BATCH_SIZE):
        s = MagicMock()
        s.file.path = "t.py"
        s.name = "S"
        symbols.append(s)
        
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = symbols
    mock_session.execute.return_value = mock_result
    
    with patch("src.workers.enrichment_worker.AsyncSessionLocal", return_value=mock_session), \
         patch("src.workers.enrichment_worker.LLMSummarizer") as MockLLM, \
         patch("src.workers.enrichment_worker.celery_app") as mock_celery:
         
        mock_llm = MockLLM.return_value
        mock_llm.summarize_async = AsyncMock(return_value='{"a":1, "functional_summary": "valid valid valid valid valid valid"}')
        
        # Test Case: At Limit
        task = MagicMock()
        await _enrich_batch_async(task, repository_id=1, iteration=MAX_ENRICHMENT_ITERATIONS)
        
        # Should NOT trigger next task
        mock_celery.send_task.assert_not_called()
        
        # Test Case: Before Limit
        await _enrich_batch_async(task, repository_id=1, iteration=1)
        mock_celery.send_task.assert_called()

@pytest.mark.asyncio
async def test_error_rollback():
    """Test that exception triggers rollback."""
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    
    mock_symbol = MagicMock()
    mock_symbol.name = "Test"
    mock_symbol.file.path = "t.py"
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_symbol]
    mock_session.execute.return_value = mock_result
    
    with patch("src.workers.enrichment_worker.AsyncSessionLocal", return_value=mock_session), \
         patch("src.workers.enrichment_worker.LLMSummarizer") as MockLLM:
         
        mock_llm = MockLLM.return_value
        mock_llm.summarize_async.side_effect = Exception("LLM Error")
        
        task = MagicMock()
        await _enrich_batch_async(task, repository_id=1)
        
        mock_session.commit.assert_not_called()
        mock_session.rollback.assert_called_once()

@pytest.mark.asyncio
async def test_llm_quality_validation():
    """Test that low quality JSON triggers fallback."""
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    
    mock_symbol = MagicMock()
    mock_symbol.name = "Test"
    mock_symbol.file.path = "t.py"
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_symbol]
    mock_session.execute.return_value = mock_result
    
    with patch("src.workers.enrichment_worker.AsyncSessionLocal", return_value=mock_session), \
         patch("src.workers.enrichment_worker.LLMSummarizer") as MockLLM:
         
        mock_llm = MockLLM.return_value
        # Return valid JSON but poor quality (short summary)
        mock_llm.summarize_async = AsyncMock(return_value='{"functional_summary": "short", "business_purpose": "AI Analysis"}')
        
        task = MagicMock()
        result = await _enrich_batch_async(task, repository_id=1)
        
        # Should still succeed (fallback mode)
        assert result["enriched"] == 1
        # But should contain fallback data (Unstructured)
        assert mock_symbol.ai_enrichment["business_purpose"] == "AI Analysis (Unstructured)"
