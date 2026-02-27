import os
import sys
from typing import Optional

from pydantic import model_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Skip dotenv loading during tests for deterministic secure defaults."""

        class _ConditionalDotEnvSource(DotEnvSettingsSource):
            def __call__(self) -> dict[str, object]:
                is_pytest_process = "pytest" in sys.modules or any(
                    part.endswith("pytest") for part in sys.argv
                )
                if is_pytest_process or os.getenv("PYTEST_CURRENT_TEST"):
                    return {}

                env_name = (
                    os.getenv("environment")
                    or os.getenv("ENVIRONMENT")
                    or ""
                ).strip().lower()
                if env_name == "testing":
                    return {}

                return super().__call__()

        return (
            init_settings,
            env_settings,
            _ConditionalDotEnvSource(settings_cls),
            file_secret_settings,
        )

    # Application
    app_name: str = "Axon.MCP.Server"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"

    # GitLab
    gitlab_url: str = "https://gitlab.com"
    gitlab_token: str = ""
    gitlab_group_id: Optional[str] = None
    gitlab_webhook_secret: Optional[str] = None

    # Azure DevOps
    azuredevops_url: str = "https://devops.example.org/"
    azuredevops_username: Optional[str] = None  # For NTLM: use DOMAIN\\username or just username
    azuredevops_password: Optional[str] = None  # Password or Personal Access Token (PAT)
    azuredevops_project: Optional[str] = None  # Optional: Only for test scripts, repositories store their own project names
    azuredevops_use_ntlm: bool = True  # Enable NTLM authentication for Azure DevOps
    azuredevops_ssl_verify: bool = True  # Keep TLS verification on by default; disable only for trusted self-signed environments

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
    api_secret_key: str = ""
    api_cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    api_rate_limit: int = 100

    # Security
    auth_enabled: bool = True  # Set to False for local dev
    admin_api_key: str = ""  # Main admin API key
    read_only_api_keys: list[str] = []  # List of read-only keys
    admin_password: str = ""  # Password for UI login (cookie-based)
    mcp_auth_enabled: bool = True  # Secure-by-default for MCP HTTP transport; override only for trusted local clients

    jwt_secret_key: str = ""
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

    @model_validator(mode="after")
    def validate_required_secrets(self) -> "Settings":
        """Require critical secrets outside explicit test environments."""
        if self.environment.lower() == "testing":
            # Keep tests deterministic and avoid leaking local developer secrets.
            self.gitlab_token = ""
            self.api_secret_key = ""
            self.jwt_secret_key = ""
            self.mcp_auth_enabled = True
            self.azuredevops_ssl_verify = True
            self.api_cors_origins = [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
            ]
            return self

        insecure_placeholders = {
            "dummy",
            "changeme",
            "replace-me",
            "test-token",
            "api-secret",
            "jwt-secret",
        }

        missing = [
            name
            for name, value in (
                ("gitlab_token", self.gitlab_token),
                ("api_secret_key", self.api_secret_key),
                ("jwt_secret_key", self.jwt_secret_key),
            )
            if not str(value).strip() or str(value).strip().lower() in insecure_placeholders
        ]
        if missing:
            missing_fields = ", ".join(missing)
            raise ValueError(
                f"Missing required settings for environment='{self.environment}': {missing_fields}"
            )

        return self


from functools import lru_cache


@lru_cache()
def get_settings() -> Settings:
    """Get the singleton Settings instance (lazily created).
    
    This defers instantiation until first use, avoiding import-time
    ValidationErrors when environment variables are not set (e.g. during
    test collection or CI environments).
    """
    return Settings()
