from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any, Set
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database.models import Repository

@dataclass
class PipelineMetrics:
    """Typed metrics container for the synchronization pipeline."""
    files_processed: int = 0
    chunks_created: int = 0
    symbols_created: int = 0
    embeddings_generated: int = 0
    api_endpoints_count: int = 0
    relationships_created: int = 0
    import_relationships_created: int = 0
    call_relationships_created: int = 0
    patterns_detected: int = 0
    outgoing_calls_count: int = 0
    published_events_count: int = 0
    event_subscriptions_count: int = 0
    dependencies_found: int = 0
    configs_found: int = 0
    ef_entities_found: int = 0
    services_detected: int = 0
    services_documented: int = 0
    
    def to_dict(self) -> Dict[str, int]:
        return {k: v for k, v in self.__dict__.items()}

@dataclass
class PipelineError:
    """Structured error info with traceback preservation."""
    step_name: str
    exception_type: str
    error_message: str
    traceback_str: str
    context: Optional[dict] = None

@dataclass
class PipelineContext:
    """
    Shared state across pipeline steps.
    Acts as a blackboard for steps to read/write data.
    """
    repository_id: int
    session: AsyncSession
    # Fix 5.1: Execution ID for distributed tracing
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # Core State
    repository: Optional[Repository] = None
    repo_path: Optional[Path] = None
    files: List[Path] = field(default_factory=list)
    
    # Typed Metrics (Finding 1.1)
    metrics: PipelineMetrics = field(default_factory=PipelineMetrics)
    
    # Timings & Errors
    timings: Dict[str, float] = field(default_factory=dict)
    errors: List[PipelineError] = field(default_factory=list) # Fix: Structured errors
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # State tracking for dependency validation (Finding 3.1)
    completed_steps: Set[str] = field(default_factory=set)
    available_data: Set[str] = field(default_factory=set)
    
    # Legacy compatibility property
    @property
    def files_processed(self) -> int:
        return self.metrics.files_processed
        
    @files_processed.setter
    def files_processed(self, value: int):
        self.metrics.files_processed = value
    
    @property
    def has_critical_error(self) -> bool:
        """Check if any critical error occurred (though usually we raise)."""
        return len(self.errors) > 0

    # Fix 1.2: Refresh repository object after session.expunge_all()
    async def refresh_repository(self) -> Repository:
        """Re-fetch repository object after session.expunge_all()."""
        result = await self.session.execute(
            select(Repository).where(Repository.id == self.repository_id)
        )
        self.repository = result.scalar_one()
        return self.repository
