"""
Unit tests for Celery tasks.

Tests the worker task implementations for repository synchronization,
file parsing, and embedding generation.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock, Mock
from datetime import datetime, timedelta
from pathlib import Path

from src.workers.tasks import (
    sync_repository,
    _sync_repository_async,
    _create_or_update_file,
    _generate_repository_embeddings,
    parse_file_task,
    generate_embeddings_task,
)
from src.database.models import Repository, File, Chunk, Job
from src.config.enums import (
    RepositoryStatusEnum,
    JobStatusEnum,
    LanguageEnum,
)
from src.parsers.base_parser import ParseResult, ParsedSymbol
from src.config.enums import SymbolKindEnum


@pytest.fixture
def mock_celery_task():
    """Mock Celery task."""
    task = MagicMock()
    task.request.id = "test-task-id-123"
    task.request.retries = 0
    task.update_state = MagicMock()
    task.retry = MagicMock(side_effect=Exception("Retry triggered"))
    return task


@pytest.fixture
def mock_repository():
    """Mock repository."""
    repo = MagicMock(spec=Repository)
    repo.id = 1
    repo.gitlab_project_id = 12345
    repo.name = "test-repo"
    repo.path_with_namespace = "test/repo"
    repo.url = "https://github.com/test/repo.git"
    repo.default_branch = "main"
    repo.status = RepositoryStatusEnum.PENDING
    repo.total_files = 0
    return repo


@pytest.fixture
def mock_job():
    """Mock job."""
    job = MagicMock(spec=Job)
    job.id = 1
    job.repository_id = 1
    job.job_type = "sync_repository"
    job.status = JobStatusEnum.PENDING
    job.started_at = datetime.utcnow()
    return job


@pytest.fixture
def mock_file():
    """Mock file."""
    file = MagicMock(spec=File)
    file.id = 1
    file.repository_id = 1
    file.path = "src/test.py"
    file.language = LanguageEnum.PYTHON
    file.size_bytes = 1024
    file.line_count = 50
    return file


@pytest.fixture
def mock_chunk():
    """Mock chunk."""
    chunk = MagicMock(spec=Chunk)
    chunk.id = 1
    chunk.file_id = 1
    chunk.content = "def test_function():\n    return True"
    chunk.token_count = 10
    return chunk


@pytest.fixture
def mock_parse_result():
    """Mock parse result."""
    symbol = ParsedSymbol(
        kind=SymbolKindEnum.FUNCTION,
        name="test_function",
        start_line=1,
        end_line=5,
        start_column=0,
        end_column=0,
        signature="def test_function():",
        fully_qualified_name="test_function"
    )
    
    return ParseResult(
        language=LanguageEnum.PYTHON,
        file_path="test.py",
        symbols=[symbol],
        imports=[],
        exports=[],
        parse_errors=[],
        parse_duration_ms=50.0
    )


@pytest.mark.asyncio
async def test_create_or_update_file_new_file(mock_repository):
    """Test creating a new file record."""
    session = AsyncMock()
    
    # Mock no existing file
    result_mock = AsyncMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock
    session.flush = AsyncMock()
    
    # Create temporary test file
    test_file = Path("test_temp_file.txt")
    test_file.write_text("test content\nline 2")
    
    try:
        repo_path = Path(".")
        
        with patch('src.workers.tasks.RepositoryManager') as mock_repo_manager:
            mock_manager = MagicMock()
            mock_manager.detect_language.return_value = LanguageEnum.PYTHON
            mock_repo_manager.return_value = mock_manager
            
            file_record = await _create_or_update_file(
                session,
                1,
                test_file,
                repo_path
            )
            
            # Verify file was added to session
            assert session.add.called
            assert session.flush.called
            
    finally:
        # Clean up
        if test_file.exists():
            test_file.unlink()


@pytest.mark.asyncio
async def test_create_or_update_file_existing_file(mock_file):
    """Test updating an existing file record."""
    session = AsyncMock()
    
    # Mock existing file
    result_mock = AsyncMock()
    result_mock.scalar_one_or_none.return_value = mock_file
    session.execute.return_value = result_mock
    
    # Create temporary test file
    test_file = Path("test_temp_file.txt")
    test_file.write_text("updated content\nline 2\nline 3")
    
    try:
        repo_path = Path(".")
        
        file_record = await _create_or_update_file(
            session,
            1,
            test_file,
            repo_path
        )
        
        # Verify file was updated
        assert file_record == mock_file
        assert file_record.line_count == 3
        
    finally:
        # Clean up
        if test_file.exists():
            test_file.unlink()


@pytest.mark.asyncio
async def test_generate_repository_embeddings_no_chunks():
    """Test embedding generation with no chunks."""
    session = AsyncMock()
    
    # Mock no chunks found
    result_mock = AsyncMock()
    result_mock.scalars.return_value.all.return_value = []
    session.execute.return_value = result_mock
    
    count = await _generate_repository_embeddings(session, 1)
    
    assert count == 0


@pytest.mark.asyncio
async def test_generate_repository_embeddings_success(mock_chunk):
    """Test successful embedding generation."""
    session = AsyncMock()
    
    # Mock chunks found
    result_mock = AsyncMock()
    result_mock.scalars.return_value.all.return_value = [mock_chunk]
    session.execute.return_value = result_mock
    
    with patch('src.workers.tasks.EmbeddingGenerator') as mock_generator_class:
        with patch('src.workers.tasks.PgVectorStore') as mock_store_class:
            # Mock embedding generator
            mock_generator = AsyncMock()
            mock_generator.generate_embeddings.return_value = [
                {'chunk_id': 1, 'vector': [0.1] * 768}
            ]
            mock_generator_class.return_value = mock_generator
            
            # Mock vector store
            mock_store = AsyncMock()
            mock_store.store_embeddings.return_value = 1
            mock_store_class.return_value = mock_store
            
            count = await _generate_repository_embeddings(session, 1)
            
            assert count == 1
            assert mock_generator.generate_embeddings.called
            assert mock_store.store_embeddings.called


@pytest.mark.asyncio
async def test_sync_repository_async_success(
    mock_celery_task,
    mock_repository,
    mock_parse_result
):
    """Test successful repository synchronization."""
    session = AsyncMock()
    
    # Mock repository query
    repo_result = AsyncMock()
    repo_result.scalar_one_or_none.return_value = mock_repository
    
    # Mock file query response
    mock_file_1 = MagicMock(spec=File)
    mock_file_1.id = 1
    mock_file_1.path = "test1.py"
    mock_file_1.repository_id = 1
    
    mock_file_2 = MagicMock(spec=File)
    mock_file_2.id = 2
    mock_file_2.path = "test2.py"
    mock_file_2.repository_id = 1

    # Mock file result for batching
    # First call returns [file1, file2], second call returns []
    file_batch_1 = AsyncMock()
    file_batch_1.scalars.return_value.all.return_value = [mock_file_1, mock_file_2]
    
    file_batch_empty = AsyncMock()
    file_batch_empty.scalars.return_value.all.return_value = []
    
    # Mock symbol count query
    symbol_result = AsyncMock()
    symbol_result.scalars.return_value.all.return_value = []

    # Mock session.stream for OutgoingCallExtractor
    stream_result = MagicMock()
    async def async_partitions_gen(size):
        yield [] # Yield one empty batch
        
    stream_result.partitions = lambda size: async_partitions_gen(size)
    session.stream = AsyncMock(return_value=stream_result)

    # Dynamic side_effect for execute to handle order-independence
    # Use a mutable list to simulate stateful batching for files
    file_query_count = [0]
    
    async def execute_side_effect(stmt):
        stmt_str = str(stmt).lower()
        if "from repository" in stmt_str:
            return repo_result
        elif "from job" in stmt_str:
            # Need a job result mock
            job_res = AsyncMock()
            job_obj = MagicMock(spec=Job)
            job_obj.id = 1
            job_obj.job_metadata = {}
            job_res.scalar_one.return_value = job_obj
            job_res.scalar_one_or_none.return_value = job_obj
            return job_res
        elif "from file" in stmt_str:
            # Handle keyset pagination batching
            # We assume the query contains "order by file.id" or "limit"
            if "order by file.id" in stmt_str or "limit" in stmt_str:
                if file_query_count[0] == 0:
                    file_query_count[0] += 1
                    return file_batch_1
                else:
                    return file_batch_empty
            return file_batch_empty
        elif "count" in stmt_str:
            return symbol_result
        elif "from service" in stmt_str: # Service detection / docs
             service_res = AsyncMock()
             service_res.scalars.return_value.all.return_value = []
             return service_res
        elif "sum" in stmt_str: # Size calc
             size_res = AsyncMock()
             size_res.scalar.return_value = 0
             return size_res
             
        # Default fallback
        return AsyncMock()

    session.execute.side_effect = execute_side_effect
    session.add = Mock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.expunge_all = Mock() # Mock expunge_all since we use it now

    
    # Use context manager for session
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    session_context.__aexit__.return_value = None
    
    with patch('src.workers.sync_worker.AsyncSessionLocal', return_value=session_context):
        with patch('src.workers.sync_worker.get_distributed_lock') as mock_lock_fn:
            # Mock distributed lock
            mock_lock = MagicMock()
            mock_lock.acquire.return_value.__enter__ = lambda self: True
            mock_lock.acquire.return_value.__exit__ = lambda self, *args: None
            mock_lock_fn.return_value = mock_lock
            
            with patch('src.workers.sync_worker.RepositoryManager') as mock_repo_manager:
                with patch('src.workers.sync_worker.parse_file') as mock_parse:
                    with patch('src.workers.sync_worker.KnowledgeExtractor') as mock_extractor_class:
                        with patch('src.workers.sync_worker.RelationshipBuilder') as mock_builder_class:
                            with patch('src.workers.sync_worker._generate_repository_embeddings') as mock_embed:
                                # Mock repository manager
                                mock_manager = MagicMock()
                                mock_manager.clone_or_update.return_value = Path("/tmp/test-repo")
                                mock_manager.get_file_tree.return_value = []  # No files for simplicity
                                mock_repo_manager.return_value = mock_manager
                                
                                # Mock parser
                                mock_parse.return_value = mock_parse_result
                                
                                # Mock knowledge extractor
                                from src.extractors.knowledge_extractor import ExtractionResult
                                mock_extractor = AsyncMock()
                                mock_extractor.extract_and_persist.return_value = ExtractionResult(
                                    symbols_created=1,
                                    symbols_updated=0,
                                    relations_created=0,
                                    chunks_created=1,
                                    dependencies_created=0,
                                    errors=[]
                                )
                                mock_extractor_class.return_value = mock_extractor
                                
                                # Mock relationship builder
                                mock_builder = AsyncMock()
                                mock_builder.build_cross_file_relationships.return_value = None
                                mock_builder_class.return_value = mock_builder
                                
                                # Mock embedding generation
                                mock_embed.return_value = 1
                                
                                # Run task
                                result = await _sync_repository_async(
                                    mock_celery_task,
                                    mock_repository.id
                                )
                                
                                # Verify result
                                assert result["status"] == "success"
                                assert result["repository_id"] == mock_repository.id


def test_sync_repository_task():
    """Test sync_repository Celery task wrapper."""
    with patch('src.workers.tasks.asyncio.run') as mock_run:
        mock_run.return_value = {"status": "success", "repository_id": 1}
        
        # Mock the task
        with patch.object(sync_repository, 'request') as mock_request:
            mock_request.id = "test-task-id"
            mock_request.retries = 0
            
            result = sync_repository(1)
            
            assert result["status"] == "success"
            assert mock_run.called


def test_parse_file_task():
    """Test parse_file_task Celery task wrapper."""
    with patch('src.workers.tasks.asyncio.run') as mock_run:
        mock_run.return_value = {"status": "success", "file_id": 1}
        
        # Mock the task
        with patch.object(parse_file_task, 'request') as mock_request:
            mock_request.id = "test-task-id"
            mock_request.retries = 0
            
            result = parse_file_task(1)
            
            assert result["status"] == "success"
            assert mock_run.called


def test_generate_embeddings_task():
    """Test generate_embeddings_task Celery task wrapper."""
    with patch('src.workers.tasks.asyncio.run') as mock_run:
        mock_run.return_value = {"status": "success", "embeddings_generated": 5}
        
        # Mock the task
        with patch.object(generate_embeddings_task, 'request') as mock_request:
            mock_request.id = "test-task-id"
            mock_request.retries = 0
            
            result = generate_embeddings_task([1, 2, 3, 4, 5])
            
            assert result["status"] == "success"
            assert result["embeddings_generated"] == 5
            assert mock_run.called


@pytest.mark.asyncio
async def test_sync_repository_lock_not_acquired(mock_celery_task, mock_repository):
    """Test repository sync when lock cannot be acquired."""
    session = AsyncMock()
    
    # Mock repository query
    repo_result = AsyncMock()
    repo_result.scalar_one_or_none.return_value = mock_repository
    session.execute.return_value = repo_result
    
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    session_context.__aexit__.return_value = None
    
    with patch('src.workers.tasks.get_async_session', return_value=session_context):
        with patch('src.workers.tasks.get_distributed_lock') as mock_lock_fn:
            # Mock lock not acquired
            mock_lock = MagicMock()
            mock_lock.acquire.return_value.__enter__ = lambda self: False
            mock_lock.acquire.return_value.__exit__ = lambda self, *args: None
            mock_lock_fn.return_value = mock_lock
            
            result = await _sync_repository_async(mock_celery_task, mock_repository.id)
            
            assert result["status"] == "skipped"
            assert "already being processed" in result["reason"]


@pytest.mark.asyncio
async def test_sync_repository_repository_not_found(mock_celery_task):
    """Test repository sync when repository doesn't exist."""
    session = AsyncMock()
    
    # Mock no repository found
    repo_result = AsyncMock()
    repo_result.scalar_one_or_none.return_value = None
    session.execute.return_value = repo_result
    
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    session_context.__aexit__.return_value = None
    
    with patch('src.workers.tasks.get_async_session', return_value=session_context):
        with patch('src.workers.tasks.get_distributed_lock') as mock_lock_fn:
            mock_lock = MagicMock()
            mock_lock.acquire.return_value.__enter__ = lambda self: True
            mock_lock.acquire.return_value.__exit__ = lambda self, *args: None
            mock_lock_fn.return_value = mock_lock
            
            result = await _sync_repository_async(mock_celery_task, 999)
            
            assert result["status"] == "error"
            assert "not found" in result["error"]


@pytest.mark.asyncio
async def test_sync_repository_exception_before_job_creation(mock_celery_task):
    """
    Regression test for UnboundLocalError bug.
    Test that exception handler doesn't crash when error occurs before job creation.
    """
    session = AsyncMock()
    
    # Mock database failure before repository query
    session.execute.side_effect = Exception("Database connection failed")
    
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    session_context.__aexit__.return_value = None
    
    with patch('src.workers.tasks.get_async_session', return_value=session_context):
        with patch('src.workers.tasks.get_distributed_lock') as mock_lock_fn:
            mock_lock = MagicMock()
            mock_lock.acquire.return_value.__enter__ = lambda self: True
            mock_lock.acquire.return_value.__exit__ = lambda self, *args: None
            mock_lock_fn.return_value = mock_lock
            
            # Should raise the original exception, not UnboundLocalError
            with pytest.raises(Exception, match="Database connection failed"):
                await _sync_repository_async(mock_celery_task, 1)


@pytest.mark.asyncio
async def test_sync_repository_retry_reuses_job(mock_celery_task, mock_repository):
    """
    Regression test for unique constraint violation on retry.
    Test that retries reuse the existing job record instead of creating a new one.
    """
    session = AsyncMock()
    
    # Mock existing job from previous attempt
    existing_job = MagicMock(spec=Job)
    existing_job.id = 1
    existing_job.status = JobStatusEnum.FAILED
    existing_job.celery_task_id = mock_celery_task.request.id
    
    # First call returns repository, second returns existing job
    repo_result = AsyncMock()
    repo_result.scalar_one_or_none.return_value = mock_repository
    
    job_result = AsyncMock()
    job_result.scalar_one_or_none.return_value = existing_job
    
    # Mock symbol count
    symbol_result = AsyncMock()
    symbol_result.scalar.return_value = 5
    
    session.execute.side_effect = [
        repo_result,      # Get repository
        job_result,       # Check for existing job
        symbol_result,    # Count symbols
    ]
    session.add = Mock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    session_context.__aexit__.return_value = None
    
    with patch('src.workers.tasks.get_async_session', return_value=session_context):
        with patch('src.workers.tasks.get_distributed_lock') as mock_lock_fn:
            mock_lock = MagicMock()
            mock_lock.acquire.return_value.__enter__ = lambda self: True
            mock_lock.acquire.return_value.__exit__ = lambda self, *args: None
            mock_lock_fn.return_value = mock_lock
            
            with patch('src.workers.tasks.RepositoryManager') as mock_repo_manager:
                with patch('src.workers.tasks.parse_file') as mock_parse:
                    with patch('src.workers.tasks.KnowledgeExtractor') as mock_extractor_class:
                        with patch('src.workers.tasks.RelationshipBuilder') as mock_builder_class:
                            with patch('src.workers.tasks._generate_repository_embeddings') as mock_embed:
                                # Mock repository manager
                                mock_manager = MagicMock()
                                mock_manager.clone_or_update.return_value = Path("/tmp/test-repo")
                                mock_manager.get_file_tree.return_value = []
                                mock_repo_manager.return_value = mock_manager
                                
                                # Mock other dependencies
                                from src.extractors.knowledge_extractor import ExtractionResult
                                mock_extractor = AsyncMock()
                                mock_extractor.extract_and_persist.return_value = ExtractionResult(
                                    symbols_created=1,
                                    symbols_updated=0,
                                    relations_created=0,
                                    chunks_created=1,
                                    dependencies_created=0,
                                    errors=[]
                                )
                                mock_extractor_class.return_value = mock_extractor
                                
                                mock_builder = AsyncMock()
                                mock_builder.build_cross_file_relationships.return_value = None
                                mock_builder_class.return_value = mock_builder
                                
                                mock_embed.return_value = 0
                                
                                # Run task
                                result = await _sync_repository_async(mock_celery_task, mock_repository.id)
                                
                                # Verify job was reused, not created
                                assert not session.add.called  # Should NOT add new job
                                assert existing_job.status == JobStatusEnum.COMPLETED  # Should update existing
                                assert result["status"] == "success"


@pytest.mark.asyncio
async def test_celery_auto_retry_increments_retry_count():
    """
    REGRESSION TEST for Bug #11: Celery self-retries aren't tracked.
    
    When Celery automatically retries a task (via self.retry()), the job's retry_count
    should be incremented. Manual retries from JobMonitor already increment the counter,
    so we detect which type by checking if status was PENDING.
    """
    mock_task = MagicMock()
    mock_task.request.id = "celery-task-id-123"
    mock_task.request.retries = 1
    mock_task.update_state = MagicMock()
    
    with patch('src.workers.tasks.get_async_session') as mock_get_session, \
         patch('src.workers.tasks.RepositoryManager') as mock_repo_manager_class, \
         patch('src.workers.tasks.RelationshipBuilder') as mock_rel_builder_class, \
         patch('src.workers.tasks._generate_repository_embeddings', new_callable=AsyncMock) as mock_gen_embeddings, \
         patch('src.workers.tasks._count_symbols', new_callable=AsyncMock) as mock_count_symbols, \
         patch('src.workers.tasks.get_distributed_lock') as mock_get_lock:
        
        # Setup mocks
        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__.return_value = mock_session
        
        # Create existing job record (Celery automatic retry scenario)
        existing_job = Job(
            id=1,
            repository_id=1,
            job_type="sync_repository",
            status=JobStatusEnum.FAILED,  # NOT PENDING - indicates Celery auto-retry
            celery_task_id="celery-task-id-123",
            retry_count=0,  # Was 0, should become 1
            started_at=datetime.utcnow() - timedelta(minutes=5)
        )
        
        # Create repository
        repo = Repository(
            id=1,
            url="https://github.com/test/repo.git",
            name="test-repo",
            status=RepositoryStatusEnum.FAILED
        )
        
        # Mock database queries
        repo_result = MagicMock()
        repo_result.scalar_one_or_none.return_value = repo
        
        job_result = MagicMock()
        job_result.scalar_one_or_none.return_value = existing_job
        
        pending_result = MagicMock()
        pending_result.scalar_one_or_none.return_value = None  # No pending job
        
        mock_session.execute.side_effect = [repo_result, job_result, pending_result]
        
        # Mock other components
        mock_repo_manager = MagicMock()
        mock_repo_manager.clone_or_update.return_value = Path("/fake/path")
        mock_repo_manager.get_file_tree.return_value = []  # No files to process
        mock_repo_manager_class.return_value = mock_repo_manager
        
        mock_rel_builder = MagicMock()
        mock_rel_builder.build_cross_file_relationships = AsyncMock(return_value=None)
        mock_rel_builder_class.return_value = mock_rel_builder
        
        mock_gen_embeddings.return_value = 0  # No embeddings generated (AsyncMock)
        mock_count_symbols.return_value = 0  # No symbols (AsyncMock)
        
        mock_lock = MagicMock()
        mock_lock.acquire.return_value.__enter__.return_value = True
        mock_lock.acquire.return_value.__exit__.return_value = None
        mock_get_lock.return_value = mock_lock
        
        # Run the task
        from src.workers.tasks import _sync_repository_async
        await _sync_repository_async(mock_task, repository_id=1)
        
        # CRITICAL: retry_count should have been incremented for Celery auto-retry
        assert existing_job.retry_count == 1
        assert existing_job.status == JobStatusEnum.COMPLETED


@pytest.mark.asyncio
async def test_manual_retry_does_not_double_increment_count():
    """
    REGRESSION TEST for Bug #11: Ensure manual retries don't double-increment.
    
    When JobMonitor manually retries a job, it sets status=PENDING and increments
    retry_count. The worker should detect this and NOT increment again.
    """
    mock_task = MagicMock()
    mock_task.request.id = "celery-task-id-456"
    mock_task.update_state = MagicMock()
    
    with patch('src.workers.tasks.get_async_session') as mock_get_session, \
         patch('src.workers.tasks.RepositoryManager') as mock_repo_manager_class, \
         patch('src.workers.tasks.RelationshipBuilder') as mock_rel_builder_class, \
         patch('src.workers.tasks._generate_repository_embeddings', new_callable=AsyncMock) as mock_gen_embeddings, \
         patch('src.workers.tasks._count_symbols', new_callable=AsyncMock) as mock_count_symbols, \
         patch('src.workers.tasks.get_distributed_lock') as mock_get_lock:
        
        # Setup mocks
        mock_session = AsyncMock()
        mock_get_session.return_value.__aenter__.return_value = mock_session
        
        # Create existing job record (manual retry scenario)
        existing_job = Job(
            id=2,
            repository_id=2,
            job_type="sync_repository",
            status=JobStatusEnum.PENDING,  # PENDING - indicates manual retry from JobMonitor
            celery_task_id="celery-task-id-456",
            retry_count=1,  # Already incremented by JobMonitor, should stay 1
            started_at=None
        )
        
        # Create repository
        repo = Repository(
            id=2,
            url="https://github.com/test/repo2.git",
            name="test-repo2",
            status=RepositoryStatusEnum.PENDING
        )
        
        # Mock database queries
        repo_result = MagicMock()
        repo_result.scalar_one_or_none.return_value = repo
        
        job_result = MagicMock()
        job_result.scalar_one_or_none.return_value = existing_job
        
        pending_result = MagicMock()
        pending_result.scalar_one_or_none.return_value = None
        
        mock_session.execute.side_effect = [repo_result, job_result, pending_result]
        
        # Mock other components
        mock_repo_manager = MagicMock()
        mock_repo_manager.clone_or_update.return_value = Path("/fake/path")
        mock_repo_manager.get_file_tree.return_value = []  # No files to process
        mock_repo_manager_class.return_value = mock_repo_manager
        
        mock_rel_builder = MagicMock()
        mock_rel_builder.build_cross_file_relationships = AsyncMock(return_value=None)
        mock_rel_builder_class.return_value = mock_rel_builder
        
        mock_gen_embeddings.return_value = 0  # No embeddings generated (AsyncMock)
        mock_count_symbols.return_value = 0  # No symbols (AsyncMock)
        
        mock_lock = MagicMock()
        mock_lock.acquire.return_value.__enter__.return_value = True
        mock_lock.acquire.return_value.__exit__.return_value = None
        mock_get_lock.return_value = mock_lock
        
        # Run the task
        from src.workers.tasks import _sync_repository_async
        await _sync_repository_async(mock_task, repository_id=2)
        
        # CRITICAL: retry_count should stay at 1 (not incremented to 2)
        assert existing_job.retry_count == 1
        assert existing_job.status == JobStatusEnum.COMPLETED


@pytest.mark.asyncio
async def test_job_monitor_retry_updates_celery_task_id():
    """
    Regression test for orphaned jobs on retry.
    Test that JobMonitor.retry_failed_job updates the celery_task_id to the NEW task ID.
    """
    from src.workers.job_monitor import JobMonitor
    
    session = AsyncMock()
    
    # Mock failed job
    mock_job = MagicMock(spec=Job)
    mock_job.id = 1
    mock_job.repository_id = 123
    mock_job.job_type = "sync_repository"
    mock_job.status = JobStatusEnum.FAILED
    mock_job.celery_task_id = "old-task-id-123"
    mock_job.retry_count = 0
    mock_job.max_retries = 3
    mock_job.job_metadata = {}
    
    # Mock repository
    mock_repo = MagicMock(spec=Repository)
    mock_repo.status = RepositoryStatusEnum.FAILED
    
    job_result = AsyncMock()
    job_result.scalar_one_or_none.return_value = mock_job
    
    repo_result = AsyncMock()
    repo_result.scalar_one_or_none.return_value = mock_repo
    
    session.execute.side_effect = [job_result, repo_result]
    session.commit = AsyncMock()
    
    # Mock the Celery task
    with patch('src.workers.job_monitor.sync_repository') as mock_sync_task:
        # Mock apply_async to succeed (new API)
        mock_sync_task.apply_async.return_value = None
        
        monitor = JobMonitor(session)
        result = await monitor.retry_failed_job(mock_job.id)
        
        # Verify retry initiated
        assert result is True
        assert mock_sync_task.apply_async.called
        
        # Verify apply_async was called with pre-generated UUID as task_id
        call_kwargs = mock_sync_task.apply_async.call_args[1]
        assert 'task_id' in call_kwargs
        task_id = call_kwargs['task_id']
        
        # Verify task_id is a valid UUID format
        assert len(task_id) == 36  # UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        assert task_id != "old-task-id-123"  # Not the old ID
        
        # CRITICAL: Verify celery_task_id was updated to the pre-generated UUID
        assert mock_job.celery_task_id == task_id, \
            "celery_task_id must be updated to pre-generated UUID before queueing to prevent race conditions"
        
        # Verify old task ID was replaced
        assert mock_job.celery_task_id != "old-task-id-123"
        
        # Verify commit was called
        assert session.commit.called


@pytest.mark.asyncio
async def test_count_symbols_efficient():
    """
    Regression test for inefficient symbol counting.
    Test that _count_symbols uses SQL COUNT instead of loading all rows.
    """
    from src.workers.tasks import _count_symbols
    from sqlalchemy import func
    
    session = AsyncMock()
    
    # Mock result with count
    result_mock = AsyncMock()
    result_mock.scalar.return_value = 42
    session.execute.return_value = result_mock
    
    count = await _count_symbols(session, 1)
    
    # Verify it used COUNT query
    assert count == 42
    
    # Verify execute was called with a count query (not fetching all rows)
    call_args = session.execute.call_args[0][0]
    # The query should contain func.count
    query_str = str(call_args)
    assert "count" in query_str.lower()


@pytest.mark.asyncio
async def test_extraction_result_dataclass_access():
    """
    Regression test for ExtractionResult dataclass bug.
    Test that code uses attribute access, not .get() on ExtractionResult.
    """
    from src.workers.tasks import _sync_repository_async
    from src.extractors.knowledge_extractor import ExtractionResult
    
    mock_task = MagicMock()
    mock_task.request.id = "test-task"
    mock_task.request.retries = 0
    mock_task.update_state = MagicMock()
    
    session = AsyncMock()
    
    mock_repo = MagicMock(spec=Repository)
    mock_repo.id = 1
    mock_repo.path_with_namespace = "test/repo"
    mock_repo.default_branch = "main"
    
    repo_result = AsyncMock()
    repo_result.scalar_one_or_none.return_value = mock_repo
    
    job_result = AsyncMock()
    job_result.scalar_one_or_none.return_value = None
    
    symbol_result = AsyncMock()
    symbol_result.scalar.return_value = 1
    
    session.execute.side_effect = [repo_result, job_result, symbol_result]
    session.add = Mock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    session_context.__aexit__.return_value = None
    
    with patch('src.workers.tasks.get_async_session', return_value=session_context):
        with patch('src.workers.tasks.get_distributed_lock') as mock_lock_fn:
            mock_lock = MagicMock()
            mock_lock.acquire.return_value.__enter__ = lambda self: True
            mock_lock.acquire.return_value.__exit__ = lambda self, *args: None
            mock_lock_fn.return_value = mock_lock
            
            with patch('src.workers.tasks.RepositoryManager') as mock_repo_manager:
                with patch('src.workers.tasks.parse_file'):
                    with patch('src.workers.tasks.KnowledgeExtractor') as mock_extractor_class:
                        with patch('src.workers.tasks.RelationshipBuilder'):
                            with patch('src.workers.tasks._generate_repository_embeddings'):
                                mock_manager = MagicMock()
                                mock_manager.clone_or_update.return_value = Path("/tmp/test")
                                mock_manager.get_file_tree.return_value = [Path("/tmp/test/file.py")]
                                mock_manager.detect_language.return_value = LanguageEnum.PYTHON
                                mock_repo_manager.return_value = mock_manager
                                
                                # Return ExtractionResult dataclass (not dict!)
                                mock_extractor = AsyncMock()
                                mock_extractor.extract_and_persist.return_value = ExtractionResult(
                                    symbols_created=5,
                                    symbols_updated=2,
                                    relations_created=3,
                                    chunks_created=10,
                                    errors=[]
                                )
                                mock_extractor_class.return_value = mock_extractor
                                
                                # Should NOT raise AttributeError when accessing .chunks_created
                                result = await _sync_repository_async(mock_task, 1)
                                assert result["status"] == "success"


@pytest.mark.asyncio
async def test_job_retry_clears_completion_metadata():
    """
    Regression test for stale completion metadata on retry.
    Test that retry clears completed_at and duration_seconds.
    """
    from src.workers.tasks import _sync_repository_async
    
    mock_task = MagicMock()
    mock_task.request.id = "test-task"
    mock_task.request.retries = 0
    mock_task.update_state = MagicMock()
    
    session = AsyncMock()
    
    mock_repo = MagicMock(spec=Repository)
    mock_repo.id = 1
    mock_repo.path_with_namespace = "test/repo"
    mock_repo.default_branch = "main"
    
    # Mock existing failed job with completion metadata
    mock_job = MagicMock(spec=Job)
    mock_job.id = 1
    mock_job.status = JobStatusEnum.FAILED
    mock_job.started_at = datetime.utcnow()
    mock_job.completed_at = datetime.utcnow()  # Has old completion time
    mock_job.duration_seconds = 300  # Has old duration
    mock_job.retry_count = 0
    
    repo_result = AsyncMock()
    repo_result.scalar_one_or_none.return_value = mock_repo
    
    job_result = AsyncMock()
    job_result.scalar_one_or_none.return_value = mock_job  # Existing job
    
    symbol_result = AsyncMock()
    symbol_result.scalar.return_value = 0
    
    session.execute.side_effect = [repo_result, job_result, symbol_result]
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    session_context.__aexit__.return_value = None
    
    with patch('src.workers.tasks.get_async_session', return_value=session_context):
        with patch('src.workers.tasks.get_distributed_lock') as mock_lock_fn:
            mock_lock = MagicMock()
            mock_lock.acquire.return_value.__enter__ = lambda self: True
            mock_lock.acquire.return_value.__exit__ = lambda self, *args: None
            mock_lock_fn.return_value = mock_lock
            
            with patch('src.workers.tasks.RepositoryManager') as mock_repo_manager:
                with patch('src.workers.tasks.parse_file'):
                    with patch('src.workers.tasks.KnowledgeExtractor'):
                        with patch('src.workers.tasks.RelationshipBuilder'):
                            with patch('src.workers.tasks._generate_repository_embeddings'):
                                mock_manager = MagicMock()
                                mock_manager.clone_or_update.return_value = Path("/tmp/test")
                                mock_manager.get_file_tree.return_value = []
                                mock_repo_manager.return_value = mock_manager
                                
                                await _sync_repository_async(mock_task, 1)
                                
                                # Verify old metadata was cleared
                                assert mock_job.completed_at is None, "completed_at should be cleared on retry"
                                assert mock_job.duration_seconds is None, "duration_seconds should be cleared on retry"
                                assert mock_job.retry_count == 1, "retry_count should be incremented"
                                assert mock_job.status == JobStatusEnum.COMPLETED


@pytest.mark.asyncio
async def test_exception_handler_rolls_back_before_commit():
    """
    Regression test for PendingRollbackError bug.
    Test that exception handler rolls back before attempting to commit failure status.
    """
    from src.workers.tasks import _sync_repository_async
    
    mock_task = MagicMock()
    mock_task.request.id = "test-task"
    mock_task.request.retries = 0
    
    session = AsyncMock()
    
    mock_repo = MagicMock(spec=Repository)
    mock_repo.id = 1
    
    mock_job = MagicMock(spec=Job)
    mock_job.id = 1
    mock_job.started_at = datetime.utcnow()
    
    repo_result = AsyncMock()
    repo_result.scalar_one_or_none.return_value = mock_repo
    
    job_result = AsyncMock()
    job_result.scalar_one_or_none.return_value = None
    
    # Simulate DB error during processing
    session.execute.side_effect = [repo_result, job_result, Exception("Flush failed")]
    session.add = Mock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()  # Track rollback calls
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    session_context.__aexit__.return_value = None
    
    with patch('src.workers.tasks.get_async_session', return_value=session_context):
        with patch('src.workers.tasks.get_distributed_lock') as mock_lock_fn:
            mock_lock = MagicMock()
            mock_lock.acquire.return_value.__enter__ = lambda self: True
            mock_lock.acquire.return_value.__exit__ = lambda self, *args: None
            mock_lock_fn.return_value = mock_lock
            
            with pytest.raises(Exception, match="Flush failed"):
                await _sync_repository_async(mock_task, 1)
            
            # Verify rollback was called before commit in exception handler
            assert session.rollback.called, "Rollback should be called in exception handler"
            
            # Verify commit was still attempted (to persist failure status)
            assert session.commit.called, "Commit should be called after rollback to persist failure"

