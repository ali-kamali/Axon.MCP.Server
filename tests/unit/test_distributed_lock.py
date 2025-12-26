"""
Unit tests for distributed locking.

Tests the Redis-based distributed locking mechanism used by workers.
"""

import pytest
from unittest.mock import patch, MagicMock
from src.workers.distributed_lock import DistributedLock, get_distributed_lock


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis_client = MagicMock()
    redis_client.ping.return_value = True
    redis_client.set.return_value = True
    redis_client.delete.return_value = 1
    redis_client.exists.return_value = 0
    redis_client.ttl.return_value = 300
    redis_client.expire.return_value = True
    return redis_client


def test_distributed_lock_initialization_success(mock_redis):
    """Test successful distributed lock initialization."""
    with patch('src.workers.distributed_lock.redis.from_url', return_value=mock_redis):
        lock = DistributedLock()
        
        assert lock.redis_client is not None
        assert mock_redis.ping.called


def test_distributed_lock_initialization_failure():
    """Test distributed lock initialization with connection failure."""
    with patch('src.workers.distributed_lock.redis.from_url', side_effect=Exception("Connection failed")):
        lock = DistributedLock()
        
        assert lock.redis_client is None


def test_acquire_lock_success(mock_redis):
    """Test successfully acquiring a lock."""
    with patch('src.workers.distributed_lock.redis.from_url', return_value=mock_redis):
        lock = DistributedLock()
        
        with lock.acquire("test-resource", timeout=300) as acquired:
            assert acquired is True
            assert mock_redis.set.called
        
        # Verify lock was released
        assert mock_redis.delete.called


def test_acquire_lock_already_locked(mock_redis):
    """Test lock acquisition when resource is already locked."""
    mock_redis.set.return_value = False  # Lock not acquired
    
    with patch('src.workers.distributed_lock.redis.from_url', return_value=mock_redis):
        lock = DistributedLock()
        
        with lock.acquire("test-resource", timeout=300) as acquired:
            assert acquired is False


def test_acquire_lock_no_redis():
    """Test lock acquisition when Redis is not available."""
    with patch('src.workers.distributed_lock.redis.from_url', side_effect=Exception("Connection failed")):
        lock = DistributedLock()
        
        # Should proceed without lock
        with lock.acquire("test-resource") as acquired:
            assert acquired is True


def test_is_locked(mock_redis):
    """Test checking if resource is locked."""
    mock_redis.exists.return_value = 1
    
    with patch('src.workers.distributed_lock.redis.from_url', return_value=mock_redis):
        lock = DistributedLock()
        
        is_locked = lock.is_locked("test-resource")
        
        assert is_locked is True
        assert mock_redis.exists.called


def test_is_locked_not_locked(mock_redis):
    """Test checking unlocked resource."""
    mock_redis.exists.return_value = 0
    
    with patch('src.workers.distributed_lock.redis.from_url', return_value=mock_redis):
        lock = DistributedLock()
        
        is_locked = lock.is_locked("test-resource")
        
        assert is_locked is False


def test_extend_lock_success(mock_redis):
    """Test extending lock expiration."""
    mock_redis.ttl.return_value = 100  # 100 seconds remaining
    
    with patch('src.workers.distributed_lock.redis.from_url', return_value=mock_redis):
        lock = DistributedLock()
        
        result = lock.extend_lock("test-resource", 200)
        
        assert result is True
        assert mock_redis.ttl.called
        assert mock_redis.expire.called


def test_extend_lock_not_found(mock_redis):
    """Test extending non-existent lock."""
    mock_redis.ttl.return_value = -2  # Key does not exist
    
    with patch('src.workers.distributed_lock.redis.from_url', return_value=mock_redis):
        lock = DistributedLock()
        
        result = lock.extend_lock("test-resource", 200)
        
        assert result is False


def test_get_distributed_lock_singleton():
    """Test that get_distributed_lock returns singleton instance."""
    with patch('src.workers.distributed_lock.redis.from_url'):
        lock1 = get_distributed_lock()
        lock2 = get_distributed_lock()
        
        assert lock1 is lock2


def test_lock_release_error_handling(mock_redis):
    """Test lock release with error."""
    mock_redis.delete.side_effect = Exception("Delete failed")
    
    with patch('src.workers.distributed_lock.redis.from_url', return_value=mock_redis):
        lock = DistributedLock()
        
        # Should not raise exception
        with lock.acquire("test-resource") as acquired:
            assert acquired is True
        
        # Error should be logged but not raised


def test_lock_acquisition_error_handling(mock_redis):
    """Test lock acquisition with error."""
    mock_redis.set.side_effect = Exception("Set failed")
    
    with patch('src.workers.distributed_lock.redis.from_url', return_value=mock_redis):
        lock = DistributedLock()
        
        # Should proceed despite error
        with lock.acquire("test-resource") as acquired:
            assert acquired is True


def test_lock_with_custom_timeout(mock_redis):
    """Test lock with custom timeout."""
    with patch('src.workers.distributed_lock.redis.from_url', return_value=mock_redis):
        lock = DistributedLock()
        
        with lock.acquire("test-resource", timeout=600) as acquired:
            assert acquired is True
            
            # Verify timeout parameter was passed
            call_args = mock_redis.set.call_args
            assert call_args[1]['ex'] == 600

