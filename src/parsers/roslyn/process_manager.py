import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Union
import psutil
import json
from src.utils.logging_config import get_logger
from src.utils.metrics import (
    roslyn_uptime_seconds,
    roslyn_failures_total,
    roslyn_requests_total,
    roslyn_memory_mb
)

logger = get_logger(__name__)

@dataclass
class ProcessHealth:
    """Health metrics for Roslyn process."""
    pid: int
    uptime_seconds: float
    request_count: int
    failure_count: int
    last_response_time: float
    memory_mb: float
    is_healthy: bool

class RoslynProcessManager:
    """
    Manages the lifecycle of a single Roslyn analyzer process.
    
    Responsibilities:
    - Start/stop process
    - Health monitoring
    - Automatic restart on failure
    - Metrics collection
    """
    
    def __init__(self, analyzer_path: Path, max_failures: int = 3):
        self.analyzer_path = analyzer_path
        self.max_failures = max_failures
        
        # Process state
        self._process: Optional[asyncio.subprocess.Process] = None
        self._process_lock = asyncio.Lock()
        self._started_at: Optional[datetime] = None
        
        # Health tracking
        self._request_count = 0
        self._failure_count = 0
        self._last_request_at: Optional[datetime] = None
        self._consecutive_failures = 0
        
        # Heartbeat
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._heartbeat_interval = 30  # seconds
        self._request_lock = asyncio.Lock() # Lock for atomic request/response
        
    async def start(self) -> bool:
        """Start the Roslyn analyzer process."""
        async with self._process_lock:
            if self._is_running():
                return True
            
            try:
                # Resolve absolute path for robustness
                exe_path = self.analyzer_path.resolve()
                if not exe_path.exists():
                    logger.error("roslyn_executable_not_found", path=str(exe_path))
                    return False

                logger.info("starting_roslyn_process", path=str(exe_path))
                
                if exe_path.suffix.lower() == '.dll':
                    cmd = ['dotnet', str(exe_path)]
                else:
                    cmd = [str(exe_path)]

                self._process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                self._started_at = datetime.utcnow()
                self._request_count = 0
                self._failure_count = 0
                self._consecutive_failures = 0
                
                # Start heartbeat monitoring
                if not self._heartbeat_task:
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                
                logger.info("roslyn_process_started", pid=self._process.pid)
                return True
            except Exception as e:
                logger.error("roslyn_process_start_failed", error=str(e))
                return False
    
    def _is_running(self) -> bool:
        """Check if process is running AND responsive."""
        if self._process is None:
            return False
        if self._process.returncode is not None:
            return False
        # Additional check: process exists in OS
        try:
            return psutil.Process(self._process.pid).is_running()
        except (psutil.NoSuchProcess, AttributeError):
            return False
            
    async def send_request(self, request: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
        """Send a JSON request to the process and await response."""
        if not self._is_running():
            await self.start()
            if not self._is_running():
                raise RuntimeError("Failed to start Roslyn analyzer process")
        
        try:
            async with self._request_lock:
                # Serialize request
                payload = json.dumps(request) + "\n"
                
                # Send
                # Check stdin
                if not self._process.stdin:
                     raise RuntimeError("Process stdin is None")

                self._process.stdin.write(payload.encode('utf-8'))
                await self._process.stdin.drain()
                
                # Receive
                if not self._process.stdout:
                     raise RuntimeError("Process stdout is None")

                line = await asyncio.wait_for(self._process.stdout.readline(), timeout=timeout)
                
                if not line:
                    raise RuntimeError("Process returned EOF")
                    
                response = json.loads(line.decode('utf-8'))
                
                self._request_count += 1
                self._consecutive_failures = 0
                self._last_request_at = datetime.utcnow()
                
                # Metrics
                roslyn_requests_total.labels(operation=request.get("command", "unknown")).inc()
                
                return response
            
        except asyncio.TimeoutError:
            self._failure_count += 1
            self._consecutive_failures += 1
            roslyn_failures_total.inc()
            logger.error("roslyn_request_timeout", pid=self._process.pid)
            await self.restart()
            raise
        except Exception as e:
            self._failure_count += 1
            self._consecutive_failures += 1
            roslyn_failures_total.inc()
            logger.error("roslyn_request_failed", error=str(e), pid=self._process.pid if self._process else "None")
            await self.restart()
            raise

    async def _heartbeat_loop(self):
        """Periodically ping the process to ensure it's responsive."""
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                
                # Check explicit stopped state to avoid resurrecting
                if self._process is None and self._started_at is None:
                     # Stopped intentionally
                     break

                if not self._is_running():
                    logger.warning("roslyn_process_died_detected_by_heartbeat")
                    roslyn_failures_total.inc()
                    await self.restart()
                    continue
                
                # Update Gauges
                try:
                    health = await self.get_health()
                    roslyn_uptime_seconds.set(health.uptime_seconds)
                    roslyn_memory_mb.set(health.memory_mb)
                except Exception:
                    pass

                # Send ping request
                try:
                    # We use a short timeout for ping
                    response = await asyncio.wait_for(
                        self.send_request({"command": "ping"}, timeout=5),
                        timeout=6.0 # Slightly larger than internal timeout
                    )
                    if response.get("status") != "ok":
                        logger.warning("roslyn_heartbeat_failed", response=response)
                        await self.restart()
                except Exception as e:
                     # send_request logs error and restarts, so we just log warning here
                    logger.warning("roslyn_heartbeat_check_failed", error=str(e))
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("roslyn_heartbeat_loop_error", error=str(e))
                await asyncio.sleep(5) # Backoff
    
    async def stop(self, graceful: bool = True):
        """Stop the Roslyn process gracefully or forcefully."""
        async with self._process_lock:
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                self._heartbeat_task = None
            
            if self._process is None:
                self._started_at = None
                return
            
            pid = self._process.pid
            
            if graceful:
                try:
                    # Send shutdown command (best effort)
                    # Use raw write to avoid restart loop in send_request
                    if self._process.stdin and not self._process.stdin.is_closing():
                        payload = json.dumps({"command": "shutdown"}) + "\n"
                        self._process.stdin.write(payload.encode('utf-8'))
                        await self._process.stdin.drain()
                    
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                    logger.info("roslyn_process_stopped_gracefully", pid=pid)
                except Exception as e:
                    logger.warning("roslyn_graceful_shutdown_failed", error=str(e))
                    try:
                        self._process.kill()
                    except: 
                        pass
            else:
                try:
                    self._process.kill()
                    logger.info("roslyn_process_killed", pid=pid)
                except:
                    pass
            
            self._process = None
            self._started_at = None
    
    async def restart(self):
        """Restart the process."""
        logger.info("roslyn_process_restarting")
        # Don't use graceful stop for restart if we suspect it's broken
        await self.stop(graceful=False)
        await self.start()
    
    async def get_health(self) -> ProcessHealth:
        """Get current process health metrics."""
        if not self._is_running():
            return ProcessHealth(
                pid=0,
                uptime_seconds=0.0,
                request_count=self._request_count,
                failure_count=self._failure_count,
                last_response_time=0.0,  # TODO: track
                memory_mb=0.0,
                is_healthy=False
            )
        
        uptime = (datetime.utcnow() - self._started_at).total_seconds() if self._started_at else 0.0
        
        try:
            proc = psutil.Process(self._process.pid)
            memory_info = proc.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
        except:
            memory_mb = 0.0
        
        is_healthy = (
            self._is_running() and
            self._consecutive_failures < 3 and
            memory_mb < 2048  # Increased to 2GB tolerance
        )
        
        return ProcessHealth(
            pid=self._process.pid,
            uptime_seconds=uptime,
            request_count=self._request_count,
            failure_count=self._failure_count,
            last_response_time=0.0,
            memory_mb=memory_mb,
            is_healthy=is_healthy
        )
