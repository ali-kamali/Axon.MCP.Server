from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from src.config.enums import SymbolKindEnum

class ServiceAnalysis(BaseModel):
    id: int
    name: str
    service_type: str
    description: Optional[str] = None
    framework_version: Optional[str] = None
    entry_points_count: int
    documentation_path: Optional[str] = None
    created_at: datetime

class EfEntityAnalysis(BaseModel):
    id: int
    entity_name: str
    namespace: Optional[str] = None
    table_name: Optional[str] = None
    schema_name: Optional[str] = None
    properties_count: int
    relationships_count: int
    has_primary_key: bool
    
class IntegrationAnalysis(BaseModel):
    outgoing_calls_count: int
    published_events_count: int
    event_subscriptions_count: int
    endpoint_links_count: int
    event_links_count: int
    
class IntegrationSummary(BaseModel):
    summary: IntegrationAnalysis
    top_outgoing_targets: List[Dict[str, Any]]
    top_event_topics: List[str]

class ConfigFinding(BaseModel):
    id: int
    config_key: str
    config_value: Optional[str] = None
    environment: Optional[str] = None
    is_secret: bool
    file_path: Optional[str] = None
    line_number: Optional[int] = None

class QualityMetric(BaseModel):
    category: str
    metric_name: str
    value: float
    unit: str
    status: str  # "good", "warning", "critical"
    details: Optional[str] = None

class QualityAnalysis(BaseModel):
    metrics: List[QualityMetric]
    files_with_no_symbols: int
    files_with_errors: int
    comment_ratio: float
