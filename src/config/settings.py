from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Axon.MCP.Server"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"

    # GitLab
    gitlab_url: str = "https://gitlab.com"
    gitlab_token: str
    gitlab_group_id: Optional[str] = None
    gitlab_webhook_secret: Optional[str] = None

    # Azure DevOps
    azuredevops_url: str = "https://devops.example.org/"
    azuredevops_username: Optional[str] = None  # For NTLM: use DOMAIN\\username or just username
    azuredevops_password: Optional[str] = None  # Password or Personal Access Token (PAT)
    azuredevops_project: Optional[str] = None  # Optional: Only for test scripts, repositories store their own project names
    azuredevops_use_ntlm: bool = True  # Enable NTLM authentication for Azure DevOps
    azuredevops_ssl_verify: bool = False  # SSL verification for self-hosted instances

    # Database
    database_url: str
    database_pool_size: int = 20
    database_max_overflow: int = 40
    database_pool_timeout: int = 30
    database_echo: bool = False

    # Redis
    # Note: When running in Docker, use "redis://redis:6379/0" (service name)
    #       When running locally, use "redis://localhost:6379/0"
    #       Docker Compose will override this via environment variable
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 50
    redis_cache_enabled: bool = True  # Set to False to disable Redis caching entirely

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"
    celery_task_time_limit: int = 3600
    celery_task_soft_time_limit: int = 3000

    # Embeddings
    embedding_provider: str = "local"  # "local" or "openai"
    openai_api_key: Optional[str] = None
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimension: int = 1536
    
    # LLM Summarization (Phase 2)
    llm_provider: str = "openrouter"  # "openai" or "openrouter"
    llm_model: str = "gpt-oss:120b"  # Model to use for summarization
    openrouter_api_key: Optional[str] = None  # OpenRouter API key
    ollama_base_url: str = "http://localhost:11434/v1"  # Ollama base URL
    llm_request_timeout: int = 300  # Timeout in seconds (default 5 minutes)
    local_embedding_model: str = "sentence-transformers/all-mpnet-base-v2"
    embedding_batch_size: int = 100

    # Vector Store
    vector_store_type: str = "pgvector"
    vector_similarity_threshold: float = 0.7

    # MCP Server
    mcp_transport: str = "stdio"  # "stdio" or "http"
    mcp_http_host: str = "0.0.0.0"
    mcp_http_port: int = 8001
    mcp_http_path: str = "/mcp"  # HTTP endpoint path

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    api_workers: int = 4
    api_secret_key: str
    api_cors_origins: list[str] = ["*"]
    api_rate_limit: int = 100

    # Security
    auth_enabled: bool = True  # Set to False for local dev
    admin_api_key: str = ""  # Main admin API key
    read_only_api_keys: list[str] = []  # List of read-only keys
    admin_password: str = ""  # Password for UI login (cookie-based)
    mcp_auth_enabled: bool = False  # Disable MCP auth by default for compatibility

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Repository Management
    repo_cache_dir: str = "./cache/repos"
    repo_max_size_mb: int = 1000
    repo_cleanup_days: int = 7

    # Parsing
    parse_timeout_seconds: int = 300
    parse_max_file_size_mb: int = 10

    # Extraction (automated during sync)
    extract_api_endpoints: bool = True  # Extract API endpoints automatically
    extract_imports: bool = True  # Resolve import relationships automatically
    build_call_graph: bool = True  # Build call graph relationships (can be slow)
    detect_patterns: bool = False  # Detect design patterns (optional, can be slow)
    extract_dependencies: bool = True  # Extract package dependencies (NuGet, npm, Python)
    extract_configuration: bool = True  # Extract configuration from appsettings.json, etc.
    extract_ef_entities: bool = True  # Extract EF Core entities and mappings

    # Hierarchical Service Detection (for DDD architecture visibility)
    detect_library_services: bool = True  # Detect class libraries as services for hierarchical exploration
    min_library_symbols: int = 10  # Minimum symbols required to detect a library as a service

    # Monitoring
    metrics_enabled: bool = True
    metrics_port: int = 9090
    tracing_enabled: bool = False
    tracing_endpoint: Optional[str] = None


settings = Settings()


def get_settings() -> Settings:
    """Get the settings singleton instance."""
    return settings

