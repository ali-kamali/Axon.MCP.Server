"""Unit tests for repository advisory locking."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.utils.repository_lock import RepositoryLock


@pytest.mark.asyncio
async def test_acquire_lock_success_first_attempt():
    """Lock is acquired immediately and released on context exit."""
    session = AsyncMock()
    session.execute.side_effect = [MagicMock(scalar=lambda: True), MagicMock()]

    lock = RepositoryLock(session)
    async with lock.acquire_lock(123, timeout_seconds=2) as acquired:
        assert acquired is True

    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_acquire_lock_times_out_after_retries():
    """Lock acquisition retries until timeout then yields False."""
    session = AsyncMock()
    session.execute.return_value = MagicMock(scalar=lambda: False)

    lock = RepositoryLock(session)

    with patch("src.utils.repository_lock.monotonic", side_effect=[0.0, 0.0, 0.2, 0.2]), patch(
        "src.utils.repository_lock.asyncio.sleep", new=AsyncMock()
    ) as sleep_mock:
        async with lock.acquire_lock(456, timeout_seconds=0) as acquired:
            assert acquired is False

    # No unlock call because lock was never acquired.
    assert session.execute.await_count == 1
    sleep_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_is_locked_returns_false_when_lock_available():
    """is_locked acquires and immediately releases when unlocked."""
    session = AsyncMock()
    session.execute.side_effect = [MagicMock(scalar=lambda: True), MagicMock()]

    lock = RepositoryLock(session)
    assert await lock.is_locked(789) is False
    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_is_locked_returns_true_when_lock_held_elsewhere():
    """is_locked returns True when advisory lock cannot be acquired."""
    session = AsyncMock()
    session.execute.return_value = MagicMock(scalar=lambda: False)

    lock = RepositoryLock(session)
    assert await lock.is_locked(789) is True
    assert session.execute.await_count == 1
