from typing import Dict, List, Optional
from pydantic import BaseModel

class SymbolDistribution(BaseModel):
    kind: str
    count: int

class LanguageDistribution(BaseModel):
    language: str
    file_count: int
    size_bytes: int

class RelationshipDistribution(BaseModel):
    relation_type: str
    count: int

class RepositoryStatistics(BaseModel):
    repository_id: int
    repository_name: str
    
    # Basic Counts
    total_files: int
    total_symbols: int
    total_endpoints: int
    total_outgoing_calls: int
    total_published_events: int
    total_event_subscriptions: int
    total_module_summaries: int
    
    # Quality Metrics
    files_with_no_symbols: int
    avg_symbols_per_file: float
    
    # Distributions
    symbol_distribution: List[SymbolDistribution]
    language_distribution: List[LanguageDistribution]
    relationship_distribution: List[RelationshipDistribution]

class OverviewStatistics(BaseModel):
    total_repositories: int
    total_files: int
    total_symbols: int
    total_endpoints: int
    total_outgoing_calls: int
    total_published_events: int
    total_event_subscriptions: int
    
    # Aggregated Distributions (Top 10)
    top_languages: List[LanguageDistribution]
