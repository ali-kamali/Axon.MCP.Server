"""Worker schemas for API requests and responses."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from src.config.enums import WorkerStatusEnum


class WorkerResponse(BaseModel):
    """Worker response schema."""

    id: str
    hostname: str
    status: WorkerStatusEnum
    current_job_id: Optional[int]
    last_heartbeat_at: Optional[datetime]
    queues: Optional[list[str]]
    started_at: Optional[datetime]

    model_config = {"from_attributes": True}

