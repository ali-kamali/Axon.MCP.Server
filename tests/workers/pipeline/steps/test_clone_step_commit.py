import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import UTC, datetime

from src.workers.pipeline.steps.clone_step import CloneStep
from src.workers.pipeline.context import PipelineContext
from src.database.models import Repository, Commit
from src.config.enums import SourceControlProviderEnum

@pytest.mark.asyncio
async def test_clone_step_extracts_commit_info():
    """Test that CloneStep extracts and persists commit info after cloning."""
    
    # Setup Context
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    # Mock execute result
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result
    
    repository = Repository(
        id=1,
        provider=SourceControlProviderEnum.GITLAB,
        url="https://gitlab.com/test/repo.git",
        clone_url="https://gitlab.com/test/repo.git",
        path_with_namespace="test/repo",
        default_branch="main"
    )
    
    ctx = PipelineContext(repository_id=1, session=mock_session, metrics=MagicMock())
    ctx.repository = repository
    
    # Mock Managers
    with patch("src.workers.pipeline.steps.clone_step.RepositoryManager") as MockGitLabManager, \
         patch("src.workers.pipeline.steps.clone_step.RedisLogPublisher") as MockPublisher, \
         patch("src.workers.pipeline.steps.clone_step.logger") as mock_logger:
        
        # Setup Publisher Mock
        mock_publisher = MockPublisher.return_value
        mock_publisher.publish_log = AsyncMock()
        mock_publisher.connect = AsyncMock()
        mock_publisher.close = AsyncMock()
        
        mock_manager = MockGitLabManager.return_value
        
        # Mock cloning
        mock_manager.clone_or_update.return_value = "/tmp/repo"
        
        # Mock commit info
        now = datetime.now(UTC).replace(tzinfo=None)
        commit_info = {
            "sha": "test_sha_123",
            "message": "Initial commit",
            "author_name": "Test User",
            "author_email": "test@example.com",
            "committed_date": now,
            "parent_sha": None
        }
        mock_manager.get_head_commit.return_value = commit_info
        
        # Execute Step
        step = CloneStep()
        await step.execute(ctx)
        
        # Check for errors
        if mock_logger.error.called:
            print(f"Logger error called: {mock_logger.error.call_args}")
        
        # Verify Manager Calls
        mock_manager.clone_or_update.assert_called_once()
        mock_manager.get_head_commit.assert_called_once_with("/tmp/repo")
        
        # Verify Repository Update
        assert ctx.repository.last_commit_sha == "test_sha_123"
        
        # Verify Commit Creation
        # Should have added a Commit object to session
        assert mock_session.add.called
        added_obj = mock_session.add.call_args[0][0]
        assert isinstance(added_obj, Commit)
        assert added_obj.sha == "test_sha_123"
        assert added_obj.repository_id == 1
        assert added_obj.message == "Initial commit"

@pytest.mark.asyncio
async def test_clone_step_handles_existing_commit():
    """Test that CloneStep handles existing commit gracefully."""
    
    # Setup Context
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    # Mock execute result for existing commit check (return existing object)
    existing_commit = Commit(id=10, sha="existing_sha")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_commit
    mock_session.execute.return_value = mock_result
    
    repository = Repository(
        id=1,
        provider=SourceControlProviderEnum.GITLAB,
        url="https://gitlab.com/test/repo.git", 
        clone_url="https://gitlab.com/test/repo.git",
        path_with_namespace="test/repo",
        default_branch="main"
    )
    
    ctx = PipelineContext(repository_id=1, session=mock_session, metrics=MagicMock())
    ctx.repository = repository
    
    with patch("src.workers.pipeline.steps.clone_step.RepositoryManager") as MockGitLabManager, \
         patch("src.workers.pipeline.steps.clone_step.RedisLogPublisher") as MockPublisher:
        
        # Setup Publisher Mock
        mock_publisher = MockPublisher.return_value
        mock_publisher.publish_log = AsyncMock()
        mock_publisher.connect = AsyncMock()
        mock_publisher.close = AsyncMock()

        mock_manager = MockGitLabManager.return_value
        mock_manager.clone_or_update.return_value = "/tmp/repo"
        
        commit_info = {
            "sha": "existing_sha",
            "message": "Existing commit",
            "author_name": "User",
            "author_email": "user@email.com",
            "committed_date": datetime.now(UTC).replace(tzinfo=None),
            "parent_sha": None
        }
        mock_manager.get_head_commit.return_value = commit_info
        
        # Execute
        step = CloneStep()
        await step.execute(ctx)
        
        # Verify Repository Update (should still happen)
        assert ctx.repository.last_commit_sha == "existing_sha"
        
        # Verify session.add was NOT called (no new commit)
        assert not mock_session.add.called
