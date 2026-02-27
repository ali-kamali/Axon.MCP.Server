"""
Unit tests for job monitoring.

Tests the JobMonitor class for managing and monitoring background jobs.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import UTC, datetime, timedelta
from src.workers.job_monitor import JobMonitor
from src.database.models import Job, Repository
from src.config.enums import JobStatusEnum, RepositoryStatusEnum


@pytest.fixture
def mock_session():
    """Mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.delete = AsyncMock()
    return session


@pytest.fixture
def mock_running_job():
    """Mock running job."""
    job = MagicMock()
    job.id = 1
    job.repository_id = 1
    job.job_type = "sync_repository"
    job.status = JobStatusEnum.RUNNING
    job.celery_task_id = "test-task-123"
    job.started_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=30)
    job.max_retries = 3
    job.retry_count = 0
    job.job_metadata = {"file_id": 123}
    return job


@pytest.fixture
def mock_failed_job():
    """Mock failed job."""
    job = MagicMock()
    job.id = 2
    job.repository_id = 1
    job.job_type = "sync_repository"
    job.status = JobStatusEnum.FAILED
    job.celery_task_id = "test-task-456"
    job.started_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    job.completed_at = datetime.now(UTC).replace(tzinfo=None)
    job.max_retries = 3
    job.retry_count = 0
    return job


@pytest.mark.asyncio
async def test_get_running_jobs(mock_session, mock_running_job):
    """Test getting running jobs."""
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [mock_running_job]
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute.return_value = result_mock
    
    monitor = JobMonitor(mock_session)
    jobs = await monitor.get_running_jobs()
    
    assert len(jobs) == 1
    assert jobs[0].status == JobStatusEnum.RUNNING


@pytest.mark.asyncio
async def test_get_pending_jobs(mock_session):
    """Test getting pending jobs."""
    pending_job = MagicMock()
    pending_job.status = JobStatusEnum.PENDING
    
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [pending_job]
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute.return_value = result_mock
    
    monitor = JobMonitor(mock_session)
    jobs = await monitor.get_pending_jobs()
    
    assert len(jobs) == 1
    assert jobs[0].status == JobStatusEnum.PENDING


@pytest.mark.asyncio
async def test_get_failed_jobs(mock_session, mock_failed_job):
    """Test getting failed jobs."""
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [mock_failed_job]
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute.return_value = result_mock
    
    monitor = JobMonitor(mock_session)
    jobs = await monitor.get_failed_jobs(limit=10)
    
    assert len(jobs) == 1
    assert jobs[0].status == JobStatusEnum.FAILED


@pytest.mark.asyncio
async def test_get_stuck_jobs(mock_session, mock_running_job):
    """Test detecting stuck jobs."""
    # Set job start time to 2 hours ago (should be stuck)
    mock_running_job.started_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2)
    
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [mock_running_job]
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute.return_value = result_mock
    
    monitor = JobMonitor(mock_session)
    stuck_jobs = await monitor.get_stuck_jobs(timeout_minutes=60)
    
    assert len(stuck_jobs) == 1


@pytest.mark.asyncio
async def test_mark_job_as_stuck(mock_session, mock_running_job):
    """Test marking a job as stuck."""
    # Mock job query
    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = mock_running_job
    
    # Mock repository query
    mock_repo = MagicMock()
    mock_repo.status = RepositoryStatusEnum.PARSING
    repo_result = MagicMock()
    repo_result.scalar_one_or_none.return_value = mock_repo
    
    mock_session.execute.side_effect = [job_result, repo_result]
    
    monitor = JobMonitor(mock_session)
    result = await monitor.mark_job_as_stuck(mock_running_job.id)
    
    assert result is True
    assert mock_running_job.status == JobStatusEnum.FAILED
    assert mock_running_job.completed_at is not None
    assert mock_session.commit.called


@pytest.mark.asyncio
async def test_mark_job_as_stuck_not_found(mock_session):
    """Test marking non-existent job as stuck."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = result_mock
    
    monitor = JobMonitor(mock_session)
    result = await monitor.mark_job_as_stuck(999)
    
    assert result is False


@pytest.mark.asyncio
async def test_retry_failed_job_success(mock_session, mock_failed_job):
    """Test successfully retrying a failed job."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_failed_job
    mock_session.execute.return_value = result_mock
    
    with patch('src.workers.tasks.sync_repository') as mock_task:
        mock_task.delay = MagicMock()
        
        monitor = JobMonitor(mock_session)
        result = await monitor.retry_failed_job(mock_failed_job.id)
        
        assert result is True
        assert mock_failed_job.status == JobStatusEnum.PENDING
        assert mock_failed_job.retry_count == 1
        assert mock_session.commit.called


@pytest.mark.asyncio
async def test_retry_failed_job_max_retries_exceeded(mock_session, mock_failed_job):
    """Test retrying job that has exceeded max retries."""
    mock_failed_job.retry_count = 3
    mock_failed_job.max_retries = 3
    
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_failed_job
    mock_session.execute.return_value = result_mock
    
    monitor = JobMonitor(mock_session)
    result = await monitor.retry_failed_job(mock_failed_job.id)
    
    assert result is False


@pytest.mark.asyncio
async def test_retry_job_not_failed(mock_session, mock_running_job):
    """Test retrying a job that is not failed."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_running_job
    mock_session.execute.return_value = result_mock
    
    monitor = JobMonitor(mock_session)
    result = await monitor.retry_failed_job(mock_running_job.id)
    
    assert result is False


@pytest.mark.asyncio
async def test_cancel_job_success(mock_session, mock_running_job):
    """Test successfully cancelling a job."""
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = mock_running_job
    mock_session.execute.return_value = result_mock
    
    with patch('src.workers.celery_app.celery_app') as mock_celery:
        mock_celery.control.revoke = MagicMock()
        
        monitor = JobMonitor(mock_session)
        result = await monitor.cancel_job(mock_running_job.id, "User requested")
        
        assert result is True
        assert mock_running_job.status == JobStatusEnum.CANCELLED
        assert mock_running_job.completed_at is not None
        assert mock_session.commit.called


@pytest.mark.asyncio
async def test_cancel_completed_job(mock_session):
    """Test cancelling a completed job."""
    completed_job = MagicMock()
    completed_job.id = 1
    completed_job.status = JobStatusEnum.COMPLETED
    
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = completed_job
    mock_session.execute.return_value = result_mock
    
    monitor = JobMonitor(mock_session)
    result = await monitor.cancel_job(completed_job.id)
    
    assert result is False


@pytest.mark.asyncio
async def test_get_job_stats(mock_session):
    """Test getting job statistics."""
    # Create mock jobs for each status
    jobs_by_status = {
        JobStatusEnum.PENDING: [MagicMock()] * 5,
        JobStatusEnum.RUNNING: [MagicMock()] * 3,
        JobStatusEnum.COMPLETED: [MagicMock()] * 10,
        JobStatusEnum.FAILED: [MagicMock()] * 2,
        JobStatusEnum.CANCELLED: [MagicMock()] * 1,
    }
    
    def mock_execute_side_effect(*args, **kwargs):
        # Determine which status is being queried based on call order
        status = list(JobStatusEnum)[mock_session.execute.call_count - 1]
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = jobs_by_status.get(status, [])
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        return result_mock
    
    mock_session.execute.side_effect = mock_execute_side_effect
    
    monitor = JobMonitor(mock_session)
    stats = await monitor.get_job_stats()
    
    assert stats["PENDING"] == 5
    assert stats["RUNNING"] == 3
    assert stats["COMPLETED"] == 10
    assert stats["FAILED"] == 2
    assert stats["CANCELLED"] == 1
    assert stats["total"] == 21


@pytest.mark.asyncio
async def test_cleanup_old_jobs(mock_session):
    """Test cleaning up old jobs."""
    # Create old jobs
    old_jobs = [
        MagicMock(status=JobStatusEnum.COMPLETED),
        MagicMock(status=JobStatusEnum.FAILED),
    ]
    
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = old_jobs
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute.return_value = result_mock
    
    monitor = JobMonitor(mock_session)
    deleted_count = await monitor.cleanup_old_jobs(days=30)
    
    assert deleted_count == 2
    assert mock_session.delete.call_count == 2
    assert mock_session.commit.called


@pytest.mark.asyncio
async def test_retry_failed_job_queueing_failure_restores_failed_state(mock_session):
    """
    REGRESSION TEST for Bug #9: retry_failed_job leaves jobs stuck when queueing fails.
    
    When apply_async() fails (broker hiccup), the job should be restored to FAILED
    state with the old celery_task_id, not left in PENDING with an orphaned task ID.
    """
    # Create a failed job
    job = MagicMock()
    job.id = 123
    job.job_type = "sync_repository"
    job.status = JobStatusEnum.FAILED
    job.celery_task_id = "old-task-id-12345"
    job.repository_id = 456
    job.retry_count = 0
    job.error_message = "Original error"
    job.error_traceback = "Original traceback"
    job.max_retries = 3
    
    # Mock the job query
    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = job
    
    # Mock the repository query
    repo = MagicMock()
    repo.status = RepositoryStatusEnum.FAILED
    repo_result = MagicMock()
    repo_result.scalar_one_or_none.return_value = repo
    
    # Configure execute to return job first, then repo
    mock_session.execute.side_effect = [job_result, repo_result]
    
    # Mock apply_async to raise an exception (broker failure)
    with patch('src.workers.tasks.sync_repository') as mock_task:
        mock_task.apply_async.side_effect = Exception("Redis connection failed")
        
        monitor = JobMonitor(mock_session)
        result = await monitor.retry_failed_job(job_id=123)
    
    # Should return False on failure
    assert result is False
    
    # Job should be restored to FAILED state
    assert job.status == JobStatusEnum.FAILED
    
    # celery_task_id should be restored to old value
    assert job.celery_task_id == "old-task-id-12345"
    
    # Error message should explain the queueing failure
    assert "Retry failed" in job.error_message
    assert "could not queue task" in job.error_message
    
    # Should have committed the rollback
    assert mock_session.commit.call_count == 2  # Once for PENDING update, once for FAILED rollback


@pytest.mark.asyncio
async def test_retry_failed_job_missing_metadata_restores_failed_state(mock_session):
    """
    REGRESSION TEST for Bug #9: retry_failed_job leaves jobs stuck when metadata is missing.
    
    When job metadata is missing (e.g., no file_id for parse_file), the job should be
    restored to FAILED state, not left in PENDING.
    """
    # Create a parse_file job without file_id in metadata
    job = MagicMock()
    job.id = 999
    job.job_type = "parse_file"
    job.status = JobStatusEnum.FAILED
    job.celery_task_id = "old-parse-task-id"
    job.retry_count = 1
    job.job_metadata = {}  # Missing file_id!
    job.max_retries = 3
    job.repository_id = None
    
    # Mock the job query
    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = job
    
    # No repository for parse_file jobs
    repo_result = MagicMock()
    repo_result.scalar_one_or_none.return_value = None
    
    mock_session.execute.side_effect = [job_result, repo_result]
    
    monitor = JobMonitor(mock_session)
    result = await monitor.retry_failed_job(job_id=999)
    
    # Should return False
    assert result is False
    
    # Job should be restored to FAILED state
    assert job.status == JobStatusEnum.FAILED
    
    # celery_task_id should be restored to old value
    assert job.celery_task_id == "old-parse-task-id"
    
    # Error message should explain missing metadata
    assert "missing metadata" in job.error_message
    
    # Should have committed the rollback
    assert mock_session.commit.call_count == 2


@pytest.mark.asyncio
async def test_retry_failed_job_success_updates_task_id(mock_session):
    """
    Test that successful retry updates celery_task_id to new UUID and commits before queueing.
    """
    # Create a failed job
    job = MagicMock()
    job.id = 123
    job.job_type = "sync_repository"
    job.status = JobStatusEnum.FAILED
    job.celery_task_id = "old-task-id-12345"
    job.repository_id = 456
    job.retry_count = 0
    job.max_retries = 3
    
    # Mock the job query
    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = job
    
    # Mock the repository query
    repo = MagicMock()
    repo.status = RepositoryStatusEnum.FAILED
    repo_result = MagicMock()
    repo_result.scalar_one_or_none.return_value = repo
    
    mock_session.execute.side_effect = [job_result, repo_result]
    
    # Mock apply_async to succeed
    with patch('src.workers.tasks.sync_repository') as mock_task:
        mock_task.apply_async.return_value = None
        
        monitor = JobMonitor(mock_session)
        result = await monitor.retry_failed_job(job_id=123)
    
    # Should return True on success
    assert result is True
    
    # Job status should be PENDING
    assert job.status == JobStatusEnum.PENDING
    
    # celery_task_id should be updated to a new UUID (not the old one)
    assert job.celery_task_id != "old-task-id-12345"
    assert len(job.celery_task_id) == 36  # UUID format
    
    # Should have committed before queueing
    assert mock_session.commit.call_count == 1
    
    # apply_async should have been called with the new task_id
    mock_task.apply_async.assert_called_once()
    call_kwargs = mock_task.apply_async.call_args[1]
    assert call_kwargs['task_id'] == job.celery_task_id


@pytest.mark.asyncio
async def test_retry_failed_job_restores_repository_status_on_queueing_failure(mock_session):
    """
    REGRESSION TEST for Bug #10: retry_failed_job leaves repository status inconsistent.
    
    When queueing fails (broker error or missing metadata), both the job AND repository
    should be rolled back to their original states. Without this, the repository is left
    in PENDING even though no worker is running.
    """
    # Create a failed job
    job = MagicMock()
    job.id = 123
    job.job_type = "sync_repository"
    job.status = JobStatusEnum.FAILED
    job.celery_task_id = "old-task-id"
    job.repository_id = 456
    job.retry_count = 1
    job.max_retries = 3
    
    # Mock the job query
    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = job
    
    # Mock the repository query
    repo = MagicMock()
    repo.id = 456
    repo.status = RepositoryStatusEnum.FAILED  # Original status
    repo_result = MagicMock()
    repo_result.scalar_one_or_none.return_value = repo
    
    mock_session.execute.side_effect = [job_result, repo_result]
    
    # Mock apply_async to raise an exception (broker failure)
    with patch('src.workers.tasks.sync_repository') as mock_task:
        mock_task.apply_async.side_effect = Exception("Redis connection failed")
        
        monitor = JobMonitor(mock_session)
        result = await monitor.retry_failed_job(job_id=123)
    
    # Should return False on failure
    assert result is False
    
    # Job should be restored to FAILED state
    assert job.status == JobStatusEnum.FAILED
    assert job.celery_task_id == "old-task-id"
    
    # CRITICAL: Repository status should be restored to original FAILED state
    assert repo.status == RepositoryStatusEnum.FAILED
    
    # Should have committed the rollback
    assert mock_session.commit.call_count == 2


@pytest.mark.asyncio
async def test_retry_failed_job_rollsback_retry_count_on_queueing_failure(mock_session):
    """
    REGRESSION TEST for Bug #14: retry_count should be rolled back on queueing failure.
    
    When apply_async() fails (broker down), the retry_count should be rolled back
    so the job doesn't exhaust retries without ever running.
    """
    # Create a failed job
    job = MagicMock()
    job.id = 888
    job.job_type = "sync_repository"
    job.status = JobStatusEnum.FAILED
    job.celery_task_id = "old-task-xyz"
    job.repository_id = 777
    job.retry_count = 2  # Was 2
    job.max_retries = 3
    
    # Mock the job query
    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = job
    
    # Mock the repository query
    repo = MagicMock()
    repo.id = 777
    repo.status = RepositoryStatusEnum.FAILED
    repo_result = MagicMock()
    repo_result.scalar_one_or_none.return_value = repo
    
    mock_session.execute.side_effect = [job_result, repo_result]
    
    # Mock apply_async to raise an exception (broker failure)
    with patch('src.workers.tasks.sync_repository') as mock_task:
        mock_task.apply_async.side_effect = Exception("Broker connection timeout")
        
        monitor = JobMonitor(mock_session)
        result = await monitor.retry_failed_job(job_id=888)
    
    # Should return False on failure
    assert result is False
    
    # Job should be restored to FAILED state
    assert job.status == JobStatusEnum.FAILED
    
    # CRITICAL: retry_count should be rolled back to original value (2, not 3)
    assert job.retry_count == 2
    
    # celery_task_id should be restored
    assert job.celery_task_id == "old-task-xyz"
    
    # Error message should explain the queueing failure
    assert "Retry failed" in job.error_message
    assert "could not queue task" in job.error_message
    
    # Repository should also be restored
    assert repo.status == RepositoryStatusEnum.FAILED
    
    # Should have committed the rollback
    assert mock_session.commit.call_count == 2


@pytest.mark.asyncio
async def test_retry_failed_job_restores_repository_status_on_missing_metadata(mock_session):
    """
    REGRESSION TEST for Bug #10: retry_failed_job leaves repository status inconsistent.
    
    When metadata is missing and queueing can't proceed, the repository status should
    be restored along with the job status.
    """
    # Create a failed job with repository
    job = MagicMock()
    job.id = 789
    job.job_type = "sync_repository"
    job.status = JobStatusEnum.FAILED
    job.celery_task_id = "old-sync-task-id"
    job.repository_id = 999
    job.retry_count = 0
    job.max_retries = 3
    job.job_metadata = {}
    
    # Mock the job query
    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = job
    
    # Mock the repository with CLONING status (in the middle of a sync)
    repo = MagicMock()
    repo.id = 999
    repo.status = RepositoryStatusEnum.CLONING  # Original status before retry
    repo_result = MagicMock()
    repo_result.scalar_one_or_none.return_value = repo
    
    mock_session.execute.side_effect = [job_result, repo_result]
    
    # Since it's sync_repository, it should queue successfully
    # Let's test with parse_file that has missing metadata instead
    job.job_type = "parse_file"
    job.repository_id = 999  # parse_file can have repository_id too
    
    monitor = JobMonitor(mock_session)
    result = await monitor.retry_failed_job(job_id=789)
    
    # Should return False due to missing file_id
    assert result is False
    
    # Job should be restored to FAILED state
    assert job.status == JobStatusEnum.FAILED
    assert job.celery_task_id == "old-sync-task-id"
    
    # CRITICAL: Repository status should be restored to original CLONING state
    assert repo.status == RepositoryStatusEnum.CLONING
    
    # Should have committed the rollback
    assert mock_session.commit.call_count == 2

