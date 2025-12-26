"""Sync progress tracking for real-time updates."""

from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime
import json

from src.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class SyncProgress:
    """Track progress of repository synchronization."""
    
    repository_id: int
    total_files: int
    processed_files: int
    current_file: str
    status: str  # "cloning", "parsing", "extracting", "embedding", "relationships", "completed", "failed"
    started_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        data = asdict(self)
        # Convert datetime to ISO format
        data['started_at'] = self.started_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()
        return data
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())
    
    @property
    def progress_percentage(self) -> float:
        """Calculate progress percentage."""
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100


class SyncProgressTracker:
    """Tracker for sync progress with optional Redis backend."""
    
    def __init__(self, repository_id: int):
        """
        Initialize progress tracker.
        
        Args:
            repository_id: Repository ID
        """
        self.repository_id = repository_id
        self.progress = None
    
    async def start(self, total_files: int):
        """Start tracking progress."""
        self.progress = SyncProgress(
            repository_id=self.repository_id,
            total_files=total_files,
            processed_files=0,
            current_file="",
            status="cloning",
            started_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        await self._save()
    
    async def update(
        self,
        processed_files: Optional[int] = None,
        current_file: Optional[str] = None,
        status: Optional[str] = None
    ):
        """Update progress."""
        if not self.progress:
            return
        
        if processed_files is not None:
            self.progress.processed_files = processed_files
        
        if current_file is not None:
            self.progress.current_file = current_file
        
        if status is not None:
            self.progress.status = status
        
        self.progress.updated_at = datetime.utcnow()
        
        await self._save()
    
    async def complete(self):
        """Mark sync as completed."""
        if self.progress:
            self.progress.status = "completed"
            self.progress.updated_at = datetime.utcnow()
            await self._save()
    
    async def fail(self, error_message: str):
        """Mark sync as failed."""
        if self.progress:
            self.progress.status = "failed"
            self.progress.error_message = error_message
            self.progress.updated_at = datetime.utcnow()
            await self._save()
    
    async def _save(self):
        """
        Save progress to storage.
        
        Currently saves to in-memory. Can be extended to use Redis for
        real-time progress updates across multiple workers.
        """
        # TODO: Implement Redis storage for real-time progress
        # For now, just log the progress
        if self.progress:
            logger.info(
                "sync_progress_updated",
                repository_id=self.repository_id,
                progress=f"{self.progress.progress_percentage:.1f}%",
                processed=self.progress.processed_files,
                total=self.progress.total_files,
                status=self.progress.status,
                current_file=self.progress.current_file
            )
    
    async def get_progress(self) -> Optional[SyncProgress]:
        """Get current progress."""
        return self.progress

