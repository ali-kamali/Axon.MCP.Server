import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from pathlib import Path
from datetime import datetime
from src.parsers.roslyn.process_manager import RoslynProcessManager

@pytest.fixture
def mock_subprocess():
    """Mock asyncio subprocess."""
    process = AsyncMock()
    process.pid = 1234
    process.returncode = None
    process.stdin = AsyncMock()
    process.stdout = AsyncMock()
    process.stderr = AsyncMock()
    
    # Setup stdin/stdout behavior
    process.stdin.write = MagicMock()
    process.stdin.drain = AsyncMock()
    process.stdin.is_closing = MagicMock(return_value=False)
    process.stdout.readline = AsyncMock(return_value=b'{"status": "ok"}\n')
    process.wait = AsyncMock(return_value=0)
    process.kill = MagicMock()
    
    return process

@pytest.fixture
def manager():
    # Use a mock path that reports existing
    with patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.resolve", return_value=Path("resolved/path/RoslynAnalyzer.exe")):
        yield RoslynProcessManager(Path("dummy/path/RoslynAnalyzer.exe"))

@pytest.mark.asyncio
async def test_start_process_success(manager, mock_subprocess):
    # Need to patch Path.exists again inside test if fixture doesn't hold or if logic re-instantiates path
    # But manager has analyzer_path as Path object.
    # The code calls self.analyzer_path.resolve().exists().
    
    with patch("asyncio.create_subprocess_exec", return_value=mock_subprocess) as mock_exec, \
         patch("src.parsers.roslyn.process_manager.psutil") as mock_psutil, \
         patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.resolve", return_value=Path("resolved/RoslynAnalyzer.exe")):
        
        mock_psutil.Process.return_value.is_running.return_value = True
        
        assert await manager.start() is True
        assert manager._process is mock_subprocess
        assert manager._heartbeat_task is not None
        assert manager._is_running() is True

@pytest.mark.asyncio
async def test_start_process_failure(manager):
    with patch("asyncio.create_subprocess_exec", side_effect=OSError("Exec failed")):
        assert await manager.start() is False
        assert manager._process is None

@pytest.mark.asyncio
async def test_stop_process_graceful(manager, mock_subprocess):
    # Setup running state
    manager._process = mock_subprocess
    manager._started_at = 100
    manager._heartbeat_task = AsyncMock()
    
    with patch("src.parsers.roslyn.process_manager.psutil"):
        await manager.stop(graceful=True)
        
        # Verify shutdown command sent
        mock_subprocess.stdin.write.assert_called()
        # Verify wait called
        mock_subprocess.wait.assert_called()
        # Verify state cleared
        assert manager._process is None
        assert manager._heartbeat_task is None

@pytest.mark.asyncio
async def test_stop_process_forceful(manager, mock_subprocess):
    # Setup running state
    manager._process = mock_subprocess
    
    await manager.stop(graceful=False)
    
    # Verify kill called
    mock_subprocess.kill.assert_called()
    assert manager._process is None

@pytest.mark.asyncio
async def test_send_request_success(manager, mock_subprocess):
    manager._process = mock_subprocess
    manager._started_at = 100
    
    with patch("src.parsers.roslyn.process_manager.psutil"):
        response = await manager.send_request({"command": "test"})
        
        assert response == {"status": "ok"}
        assert manager._request_count == 1
        assert manager._failure_count == 0

@pytest.mark.asyncio
async def test_send_request_restart_on_error(manager, mock_subprocess):
    manager._process = mock_subprocess
    
    # Mock readline to raise error
    mock_subprocess.stdout.readline.side_effect = Exception("Connection reset")
    
    with patch("src.parsers.roslyn.process_manager.psutil"), \
         patch.object(manager, "restart", new_callable=AsyncMock) as mock_restart:
        
        with pytest.raises(Exception):
            await manager.send_request({"command": "test"})
        
        assert manager._failure_count == 1
        mock_restart.assert_called_once()

@pytest.mark.asyncio
async def test_get_health(manager, mock_subprocess):
    manager._process = mock_subprocess
    manager._started_at = datetime.utcnow()
    manager._request_count = 10
    manager._failure_count = 1
    
    with patch("src.parsers.roslyn.process_manager.psutil") as mock_psutil:
        mock_proc = mock_psutil.Process.return_value
        mock_proc.is_running.return_value = True
        mock_proc.memory_info.return_value.rss = 100 * 1024 * 1024 # 100MB
        
        health = await manager.get_health()
        
        assert health.pid == 1234
        assert health.is_healthy is True
        assert health.memory_mb == 100.0
        assert health.request_count == 10
