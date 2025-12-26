"""
Integration tests for worker pipeline.

Tests the complete end-to-end repository synchronization pipeline
including cloning, parsing, extraction, and embedding generation.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

from src.workers.tasks import sync_repository, _sync_repository_async
from src.database.session import get_async_session
from src.database.models import Repository, Job, File, Symbol, Chunk, Embedding
from src.config.enums import (
    RepositoryStatusEnum,
    JobStatusEnum,
    LanguageEnum,
)
from src.parsers.base_parser import ParseResult, ParsedSymbol
from src.config.enums import SymbolKindEnum


@pytest.fixture
def mock_celery_task():
    """Mock Celery task for testing."""
    task = MagicMock()
    task.request.id = "integration-test-task-id"
    task.request.retries = 0
    task.update_state = MagicMock()
    return task


@pytest.fixture
def sample_parse_result():
    """Sample parse result for testing."""
    symbol = ParsedSymbol(
        kind=SymbolKindEnum.FUNCTION,
        name="hello_world",
        start_line=1,
        end_line=3,
        start_column=0,
        end_column=0,
        signature="def hello_world():",
        fully_qualified_name="hello_world",
        documentation="A simple hello world function"
    )
    
    return ParseResult(
        language=LanguageEnum.PYTHON,
        file_path="hello.py",
        symbols=[symbol],
        imports=[],
        exports=[],
        parse_errors=[],
        parse_duration_ms=25.0
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repository_sync_full_pipeline(mock_celery_task, sample_parse_result):
    """
    Test complete repository sync pipeline.
    
    This is a comprehensive integration test that mocks external dependencies
    but tests the full pipeline logic.
    """
    # Create test repository
    async with get_async_session() as session:
        # Check if test repo exists
        from sqlalchemy import select
        result = await session.execute(
            select(Repository).where(
                Repository.path_with_namespace == "test/integration-repo"
            )
        )
        existing_repo = result.scalar_one_or_none()
        
        if existing_repo:
            # Delete existing test repo
            await session.delete(existing_repo)
            await session.commit()
        
        # Create new test repository
        repo = Repository(
            gitlab_project_id=99999,
            name="integration-repo",
            path_with_namespace="test/integration-repo",
            url="https://github.com/test/integration-repo.git",
            default_branch="main",
            status=RepositoryStatusEnum.PENDING
        )
        session.add(repo)
        await session.commit()
        await session.refresh(repo)
        repo_id = repo.id
    
    try:
        # Mock external dependencies
        with patch('src.workers.tasks.RepositoryManager') as mock_repo_manager_class:
            with patch('src.workers.tasks.parse_file') as mock_parse:
                with patch('src.workers.tasks.EmbeddingGenerator') as mock_generator_class:
                    with patch('src.workers.tasks.PgVectorStore') as mock_store_class:
                        # Setup repository manager mock
                        mock_repo_manager = MagicMock()
                        test_repo_path = Path("/tmp/test-integration-repo")
                        mock_repo_manager.clone_or_update.return_value = test_repo_path
                        
                        # Create temporary test files
                        test_file = test_repo_path / "test.py"
                        mock_repo_manager.get_file_tree.return_value = [test_file]
                        mock_repo_manager.detect_language.return_value = LanguageEnum.PYTHON
                        mock_repo_manager_class.return_value = mock_repo_manager
                        
                        # Setup parser mock
                        mock_parse.return_value = sample_parse_result
                        
                        # Setup embedding generator mock
                        mock_generator = AsyncMock()
                        mock_generator.generate_embeddings.return_value = [
                            {
                                'chunk_id': 1,
                                'vector': [0.1] * 768,
                                'model_name': 'test-model',
                                'dimension': 768
                            }
                        ]
                        mock_generator_class.return_value = mock_generator
                        
                        # Setup vector store mock
                        mock_store = AsyncMock()
                        mock_store.store_embeddings.return_value = 1
                        mock_store_class.return_value = mock_store
                        
                        # Run the sync task
                        result = await _sync_repository_async(mock_celery_task, repo_id)
                        
                        # Verify result
                        assert result["status"] == "success"
                        assert result["repository_id"] == repo_id
                        assert result["files_processed"] == 1
                        
                        # Verify database state
                        async with get_async_session() as session:
                            # Check repository status
                            from sqlalchemy import select
                            repo_result = await session.execute(
                                select(Repository).where(Repository.id == repo_id)
                            )
                            repo = repo_result.scalar_one()
                            assert repo.status == RepositoryStatusEnum.COMPLETED
                            assert repo.last_synced_at is not None
                            
                            # Check job was created and completed
                            job_result = await session.execute(
                                select(Job)
                                .where(Job.repository_id == repo_id)
                                .order_by(Job.created_at.desc())
                            )
                            job = job_result.scalars().first()
                            assert job is not None
                            assert job.status == JobStatusEnum.COMPLETED
                            assert job.celery_task_id == mock_celery_task.request.id
                            
                            # Check file was created
                            file_result = await session.execute(
                                select(File).where(File.repository_id == repo_id)
                            )
                            files = file_result.scalars().all()
                            assert len(files) > 0
                            
                            # Check symbols were extracted
                            symbol_result = await session.execute(
                                select(Symbol)
                                .join(File)
                                .where(File.repository_id == repo_id)
                            )
                            symbols = symbol_result.scalars().all()
                            assert len(symbols) > 0
                            
                            # Check chunks were created
                            chunk_result = await session.execute(
                                select(Chunk)
                                .join(File)
                                .where(File.repository_id == repo_id)
                            )
                            chunks = chunk_result.scalars().all()
                            assert len(chunks) > 0
        
    finally:
        # Cleanup: delete test repository
        async with get_async_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(Repository).where(Repository.id == repo_id)
            )
            repo = result.scalar_one_or_none()
            if repo:
                await session.delete(repo)
                await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repository_sync_with_lock():
    """Test that distributed lock prevents concurrent processing."""
    # Create test repository
    async with get_async_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Repository).where(
                Repository.path_with_namespace == "test/lock-test-repo"
            )
        )
        existing_repo = result.scalar_one_or_none()
        
        if existing_repo:
            await session.delete(existing_repo)
            await session.commit()
        
        repo = Repository(
            gitlab_project_id=88888,
            name="lock-test-repo",
            path_with_namespace="test/lock-test-repo",
            url="https://github.com/test/lock-test-repo.git",
            default_branch="main",
            status=RepositoryStatusEnum.PENDING
        )
        session.add(repo)
        await session.commit()
        await session.refresh(repo)
        repo_id = repo.id
    
    try:
        mock_task = MagicMock()
        mock_task.request.id = "lock-test-task"
        mock_task.request.retries = 0
        mock_task.update_state = MagicMock()
        
        with patch('src.workers.tasks.get_distributed_lock') as mock_lock_fn:
            # Mock lock not acquired
            mock_lock = MagicMock()
            mock_lock.acquire.return_value.__enter__ = lambda self: False
            mock_lock.acquire.return_value.__exit__ = lambda self, *args: None
            mock_lock_fn.return_value = mock_lock
            
            result = await _sync_repository_async(mock_task, repo_id)
            
            assert result["status"] == "skipped"
            assert "already being processed" in result["reason"]
    
    finally:
        # Cleanup
        async with get_async_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(Repository).where(Repository.id == repo_id)
            )
            repo = result.scalar_one_or_none()
            if repo:
                await session.delete(repo)
                await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repository_sync_error_handling(mock_celery_task):
    """Test error handling in repository sync."""
    # Create test repository
    async with get_async_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Repository).where(
                Repository.path_with_namespace == "test/error-test-repo"
            )
        )
        existing_repo = result.scalar_one_or_none()
        
        if existing_repo:
            await session.delete(existing_repo)
            await session.commit()
        
        repo = Repository(
            gitlab_project_id=77777,
            name="error-test-repo",
            path_with_namespace="test/error-test-repo",
            url="https://github.com/test/error-test-repo.git",
            default_branch="main",
            status=RepositoryStatusEnum.PENDING
        )
        session.add(repo)
        await session.commit()
        await session.refresh(repo)
        repo_id = repo.id
    
    try:
        with patch('src.workers.tasks.RepositoryManager') as mock_repo_manager_class:
            # Make clone_or_update raise an exception
            mock_repo_manager = MagicMock()
            mock_repo_manager.clone_or_update.side_effect = Exception("Clone failed")
            mock_repo_manager_class.return_value = mock_repo_manager
            
            # Run task and expect exception
            with pytest.raises(Exception, match="Clone failed"):
                await _sync_repository_async(mock_celery_task, repo_id)
            
            # Verify repository status was updated to FAILED
            async with get_async_session() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(Repository).where(Repository.id == repo_id)
                )
                repo = result.scalar_one()
                assert repo.status == RepositoryStatusEnum.FAILED
                
                # Verify job was marked as failed
                job_result = await session.execute(
                    select(Job)
                    .where(Job.repository_id == repo_id)
                    .order_by(Job.created_at.desc())
                )
                job = job_result.scalars().first()
                assert job is not None
                assert job.status == JobStatusEnum.FAILED
                assert "Clone failed" in job.error_message
    
    finally:
        # Cleanup
        async with get_async_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(Repository).where(Repository.id == repo_id)
            )
            repo = result.scalar_one_or_none()
            if repo:
                await session.delete(repo)
                await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_progress_updates(mock_celery_task, sample_parse_result):
    """Test that task progress updates are sent."""
    # Create test repository
    async with get_async_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Repository).where(
                Repository.path_with_namespace == "test/progress-test-repo"
            )
        )
        existing_repo = result.scalar_one_or_none()
        
        if existing_repo:
            await session.delete(existing_repo)
            await session.commit()
        
        repo = Repository(
            gitlab_project_id=66666,
            name="progress-test-repo",
            path_with_namespace="test/progress-test-repo",
            url="https://github.com/test/progress-test-repo.git",
            default_branch="main",
            status=RepositoryStatusEnum.PENDING
        )
        session.add(repo)
        await session.commit()
        await session.refresh(repo)
        repo_id = repo.id
    
    try:
        with patch('src.workers.tasks.RepositoryManager') as mock_repo_manager_class:
            with patch('src.workers.tasks.parse_file') as mock_parse:
                with patch('src.workers.tasks.EmbeddingGenerator') as mock_generator_class:
                    with patch('src.workers.tasks.PgVectorStore') as mock_store_class:
                        # Setup mocks
                        mock_repo_manager = MagicMock()
                        test_repo_path = Path("/tmp/test-progress-repo")
                        mock_repo_manager.clone_or_update.return_value = test_repo_path
                        
                        # Create 15 test files to trigger progress update
                        test_files = [
                            test_repo_path / f"test{i}.py"
                            for i in range(15)
                        ]
                        mock_repo_manager.get_file_tree.return_value = test_files
                        mock_repo_manager.detect_language.return_value = LanguageEnum.PYTHON
                        mock_repo_manager_class.return_value = mock_repo_manager
                        
                        mock_parse.return_value = sample_parse_result
                        
                        mock_generator = AsyncMock()
                        mock_generator.generate_embeddings.return_value = []
                        mock_generator_class.return_value = mock_generator
                        
                        mock_store = AsyncMock()
                        mock_store.store_embeddings.return_value = 0
                        mock_store_class.return_value = mock_store
                        
                        # Run task
                        await _sync_repository_async(mock_celery_task, repo_id)
                        
                        # Verify progress updates were called
                        assert mock_celery_task.update_state.called
                        # Should be called at least once (every 10 files)
                        assert mock_celery_task.update_state.call_count >= 1
    
    finally:
        # Cleanup
        async with get_async_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(Repository).where(Repository.id == repo_id)
            )
            repo = result.scalar_one_or_none()
            if repo:
                await session.delete(repo)
                await session.commit()

