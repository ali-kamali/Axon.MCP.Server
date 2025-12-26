from typing import List, Optional
from pydantic import BaseModel


class OutgoingApiCallSample(BaseModel):
    id: int
    http_method: str
    url_pattern: str
    http_client_library: Optional[str]
    line_number: Optional[int]
    file_path: Optional[str]


class PublishedEventSample(BaseModel):
    id: int
    event_type_name: str
    messaging_library: Optional[str]
    line_number: Optional[int]
    file_path: Optional[str]


class EventSubscriptionSample(BaseModel):
    id: int
    event_type_name: str
    handler_class_name: Optional[str]
    messaging_library: Optional[str]
    line_number: Optional[int]
    file_path: Optional[str]


class EndpointSample(BaseModel):
    id: int
    name: str
    signature: Optional[str]
    documentation: Optional[str]
    line_number: int
    file_path: Optional[str]


class ModuleSummarySample(BaseModel):
    id: int
    module_name: str
    module_path: str
    summary: str
    file_count: int
    symbol_count: int


class RepositorySamples(BaseModel):
    outgoing_calls: List[OutgoingApiCallSample]
    published_events: List[PublishedEventSample]
    event_subscriptions: List[EventSubscriptionSample]
    endpoints: List[EndpointSample]
    module_summaries: List[ModuleSummarySample]
