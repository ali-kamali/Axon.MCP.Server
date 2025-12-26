"""Job schemas for API requests and responses."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from src.config.enums import JobStatusEnum


class JobResponse(BaseModel):
    """Job response schema."""

    id: int
    repository_id: Optional[int]
    job_type: str
    status: JobStatusEnum
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    retry_count: int
    max_retries: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobDetailResponse(JobResponse):
    """Detailed job response with error information."""

    celery_task_id: Optional[str]
    error_message: Optional[str]
    error_traceback: Optional[str]
    job_metadata: Optional[dict]

    model_config = {"from_attributes": True}

