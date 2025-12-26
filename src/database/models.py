from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Enum,
    Text,
    JSON,
    BigInteger,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, declarative_base
from pgvector.sqlalchemy import Vector
from src.config.enums import (
    LanguageEnum,
    SymbolKindEnum,
    AccessModifierEnum,
    RelationTypeEnum,
    RepositoryStatusEnum,
    JobStatusEnum,
    WorkerStatusEnum,
    SourceControlProviderEnum,
)


# Helper function to create enums that use .value instead of .name
def value_enum(enum_class):
    """Create an Enum type that uses the enum's .value attribute instead of .name."""
    return Enum(enum_class, values_callable=lambda x: [e.value for e in x])


Base = declarative_base()


class Repository(Base):
    """Repository metadata for multiple source control providers."""

    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True)
    provider = Column(value_enum(SourceControlProviderEnum), nullable=False, index=True, default=SourceControlProviderEnum.GITLAB)
    
    # GitLab specific fields
    gitlab_project_id = Column(Integer, index=True)
    
    # Azure DevOps specific fields
    azuredevops_project_name = Column(String(255), index=True)
    azuredevops_repo_id = Column(String(255), index=True)
    
    # Common fields
    name = Column(String(255), nullable=False)
    path_with_namespace = Column(String(500), nullable=False)
    url = Column(String(500), nullable=False)
    clone_url = Column(String(500), nullable=False)
    default_branch = Column(String(100), default="main")
    description = Column(Text)
    status = Column(value_enum(RepositoryStatusEnum), default=RepositoryStatusEnum.PENDING, index=True)
    last_synced_at = Column(DateTime)
    last_commit_sha = Column(String(40))
    total_files = Column(Integer, default=0)
    total_symbols = Column(Integer, default=0)
    size_bytes = Column(BigInteger, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Repository Aggregation (Axon v3.4)
    manifesto = Column(Text)  # REPOSITORY_MANIFESTO.md content
    ai_summary = Column(JSONB)  # Structured business overview

    # Relationships
    commits = relationship("Commit", back_populates="repository", cascade="all, delete-orphan")
    files = relationship("File", back_populates="repository", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="repository", cascade="all, delete-orphan")
    module_summaries = relationship("ModuleSummary", back_populates="repository", cascade="all, delete-orphan")
    solutions = relationship("Solution", back_populates="repository", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="repository", cascade="all, delete-orphan")
    services = relationship("Service", back_populates="repository", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_repo_status_updated", "status", "updated_at"),
        Index("idx_repo_provider_path", "provider", "path_with_namespace"),
        Index("idx_repo_gitlab_project", "gitlab_project_id"),
        Index("idx_repo_azuredevops_project_repo", "azuredevops_project_name", "azuredevops_repo_id"),
    )


class Service(Base):
    """Represents a detected service/bounded context (e.g., API, Worker)."""
    
    __tablename__ = "services"
    
    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)  # e.g., "Axon.Appointment.Service"
    service_type = Column(String(50), nullable=False, index=True)  # "API", "Worker", "Console", "Library"
    description = Column(Text)
    
    # Structural info
    root_namespace = Column(String(255))
    project_path = Column(String(1000))  # Path to .csproj or package.json
    entry_points = Column(JSON)  # List of detected controllers/endpoints
    framework_version = Column(String(50))  # e.g., "net8.0"
    
    # Documentation
    documentation_path = Column(String(1000))
    last_documented_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    repository = relationship("Repository", back_populates="services")
    symbols = relationship("Symbol", back_populates="service")


class EfEntity(Base):
    """Entity Framework Core entity mapping (table schema, properties, relationships)."""
    
    __tablename__ = "ef_entities"
    
    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Entity identification
    entity_name = Column(String(500), nullable=False, index=True)  # e.g., "Order"
    namespace = Column(String(1000))  # e.g., "Sales.Domain.Entities"
    
    # Database mapping
    table_name = Column(String(500), index=True)  # Physical table name
    schema_name = Column(String(200))  # Database schema (e.g., "dbo", "sales")
    
    # Keys and properties
    primary_keys = Column(JSON)  # ["Id"] or ["Key1", "Key2"] for composite keys
    properties = Column(JSON)  # Array of property objects with column mappings
    
    # Relationships (navigation properties)
    relationships = Column(JSON)  # Array of relationship objects (HasOne, HasMany, etc.)
    
    # Full mapping details
    raw_mapping = Column(JSON)  # Complete EF mapping configuration for reference
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("idx_ef_entity_repo", "repository_id"),
        Index("idx_ef_entity_table", "table_name"),
        Index("idx_ef_entity_name", "entity_name"),
        # Unique constraint: one entity per name per repository
        UniqueConstraint(
            "repository_id", "entity_name",
            name="uq_ef_entity_repo_name"
        ),
    )


class Commit(Base):
    """Git commit information."""

    __tablename__ = "commits"

    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    sha = Column(String(40), nullable=False, unique=True, index=True)
    message = Column(Text)
    author_name = Column(String(255))
    author_email = Column(String(255))
    committed_date = Column(DateTime)
    parent_sha = Column(String(40))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    repository = relationship("Repository", back_populates="commits")
    files = relationship("File", back_populates="commit")
    symbols = relationship("Symbol", back_populates="commit")


class File(Base):
    """Source code file."""

    __tablename__ = "files"

    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    commit_id = Column(Integer, ForeignKey("commits.id", ondelete="SET NULL"), index=True)
    path = Column(String(1000), nullable=False)
    language = Column(value_enum(LanguageEnum), nullable=False, index=True)
    size_bytes = Column(Integer, default=0)
    content_hash = Column(String(64), index=True)
    line_count = Column(Integer, default=0)
    last_modified = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    repository = relationship("Repository", back_populates="files")
    commit = relationship("Commit", back_populates="files")
    symbols = relationship("Symbol", back_populates="file", cascade="all, delete-orphan")
    chunks = relationship("Chunk", back_populates="file", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_file_repo_path", "repository_id", "path"),
        Index("idx_file_language_repo", "language", "repository_id"),
    )


class Solution(Base):
    """Visual Studio Solution (.sln file)."""
    
    __tablename__ = "solutions"
    
    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    file_path = Column(String(1000), nullable=False)
    name = Column(String(255), nullable=False)
    format_version = Column(String(50))  # e.g., "12.00"
    visual_studio_version = Column(String(50))  # e.g., "Version 17.0"
    visual_studio_full_version = Column(String(50))
    minimum_visual_studio_version = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    repository = relationship("Repository", back_populates="solutions")
    projects = relationship("Project", back_populates="solution", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_solution_repo", "repository_id"),
    )


class Project(Base):
    """Project from .sln or .csproj."""
    
    __tablename__ = "projects"
    
    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    solution_id = Column(Integer, ForeignKey("solutions.id", ondelete="SET NULL"), index=True)
    project_guid = Column(String(36), index=True)  # Visual Studio project GUID
    name = Column(String(255), nullable=False, index=True)
    file_path = Column(String(1000), nullable=False)
    project_type = Column(String(100))  # "C# Project", "Test Project", etc.
    project_type_guid = Column(String(36))
    assembly_name = Column(String(255))
    target_framework = Column(String(100))
    output_type = Column(String(50))  # "Library", "Exe", "WinExe"
    define_constants = Column(JSON)  # ["DEBUG", "TRACE"]
    lang_version = Column(String(20))  # "10.0", "latest"
    nullable_context = Column(String(50))  # "enable", "disable", etc.
    root_namespace = Column(String(255))  # Default namespace for the project
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    repository = relationship("Repository", back_populates="projects")
    solution = relationship("Solution", back_populates="projects")
    
    __table_args__ = (
        Index("idx_project_repo", "repository_id"),
        Index("idx_project_solution", "solution_id"),
        Index("idx_project_guid", "project_guid"),
        Index("idx_project_name", "name"),
    )


class Symbol(Base):
    """Code symbol (function, class, variable, etc.)."""

    __tablename__ = "symbols"

    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    commit_id = Column(Integer, ForeignKey("commits.id", ondelete="SET NULL"), index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), index=True)  # Phase 2.2
    service_id = Column(Integer, ForeignKey("services.id", ondelete="SET NULL"), index=True)  # Service Boundary
    assembly_name = Column(String(255))  # Phase 2.2
    language = Column(value_enum(LanguageEnum), nullable=False, index=True)
    kind = Column(value_enum(SymbolKindEnum), nullable=False, index=True)
    access_modifier = Column(value_enum(AccessModifierEnum))
    name = Column(String(1000), nullable=False, index=True)
    fully_qualified_name = Column(String(2000), index=True)
    start_line = Column(Integer, nullable=False)
    end_line = Column(Integer, nullable=False)
    start_column = Column(Integer)
    end_column = Column(Integer)
    signature = Column(Text)
    documentation = Column(Text)
    structured_docs = Column(JSON)  # XML/JSDoc structured documentation
    attributes = Column(JSON)  # C# attributes, TypeScript decorators
    parameters = Column(JSON)
    return_type = Column(String(1000))
    
    # Generics support (Phase 2.3)
    generic_parameters = Column(JSON)  # [{"name": "T", "variance": "out"}, ...]
    constraints = Column(JSON)  # [{"parameter": "T", "constraints": ["class", "new()"]}]
    
    parent_symbol_id = Column(Integer, ForeignKey("symbols.id", ondelete="SET NULL"), index=True)
    parent_name = Column(String(2000))  # Parent fully qualified name
    role_tags = Column(JSON)
    
    # AI Enrichment (Phase 3)
    ai_enrichment = Column(JSONB)
    complexity = Column(Integer)
    complexity_score = Column(Integer)  # Alias for compatibility
    token_count = Column(Integer)
    is_test = Column(Integer, default=0)  # Boolean: 1 if test code, 0 otherwise
    is_generated = Column(Integer, default=0)  # Boolean: 1 if generated code, 0 otherwise
    usage_count = Column(Integer, default=0)  # How many symbols reference this
    last_modified_by = Column(String(255))  # Git author from last commit
    git_blame_commit = Column(String(40))  # Commit SHA from git blame
    
    # Partial class support (Phase 2.1)
    is_partial = Column(Integer, default=0)  # Boolean: 1 if partial class/interface/struct
    partial_definition_files = Column(JSON)  # List of file_ids where this symbol is defined
    merged_from_partial_ids = Column(JSON)  # List of symbol_ids that were merged into this one
    
    # LINQ/Lambda Analysis (Phase 3.1)
    is_lambda = Column(Integer, default=0)  # Boolean: 1 if lambda expression
    closure_variables = Column(JSON)  # List of captured variable names
    linq_pattern = Column(String(100))  # "Select", "Where", "Aggregate", etc.
        
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    file = relationship("File", back_populates="symbols")
    commit = relationship("Commit", back_populates="symbols")
    service = relationship("Service", back_populates="symbols")
    embeddings = relationship("Embedding", back_populates="symbol", cascade="all, delete-orphan")
    parent = relationship("Symbol", remote_side=[id], backref="children")
    relations_from = relationship(
        "Relation",
        foreign_keys="Relation.from_symbol_id",
        back_populates="from_symbol",
        cascade="all, delete-orphan",
    )
    relations_to = relationship(
        "Relation",
        foreign_keys="Relation.to_symbol_id",
        back_populates="to_symbol",
    )

    __table_args__ = (
        Index("idx_symbol_name_kind", "name", "kind"),
        Index("idx_symbol_fqn", "fully_qualified_name"),
        Index("idx_symbol_complexity", "complexity_score"),
    )


class Relation(Base):
    """Relationship between symbols."""

    __tablename__ = "relations"

    id = Column(Integer, primary_key=True)
    from_symbol_id = Column(Integer, ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False, index=True)
    to_symbol_id = Column(Integer, ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False, index=True)
    relation_type = Column(value_enum(RelationTypeEnum), nullable=False, index=True)
    relation_metadata = Column(JSON)
    
    # Reference location (Phase 3.4)
    start_line = Column(Integer)
    end_line = Column(Integer)
    start_column = Column(Integer)
    end_column = Column(Integer)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    from_symbol = relationship("Symbol", foreign_keys=[from_symbol_id], back_populates="relations_from")
    to_symbol = relationship("Symbol", foreign_keys=[to_symbol_id], back_populates="relations_to")

    __table_args__ = (
        Index("idx_relation_from_type", "from_symbol_id", "relation_type"),
        Index("idx_relation_to_type", "to_symbol_id", "relation_type"),
    )


class Chunk(Base):
    """Code chunk for embedding."""

    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol_id = Column(Integer, ForeignKey("symbols.id", ondelete="CASCADE"), index=True)
    content = Column(Text, nullable=False)
    content_type = Column(String(50))
    chunk_subtype = Column(String(50))  # "implementation", "intent", "config", etc.
    token_count = Column(Integer, default=0)
    start_line = Column(Integer)
    end_line = Column(Integer)
    content_hash = Column(String(64), index=True)
    parent_chunk_id = Column(Integer, ForeignKey("chunks.id", ondelete="SET NULL"), index=True)  # For related chunks
    context_metadata = Column(JSON)  # Store file context, imports, namespace, etc.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    file = relationship("File", back_populates="chunks")
    embeddings = relationship("Embedding", back_populates="chunk", cascade="all, delete-orphan")


class Document(Base):
    """Markdown documentation file."""
    
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), index=True)
    path = Column(String(1000), nullable=False)
    doc_type = Column(String(50), index=True)  # 'readme', 'changelog', 'guide', 'api_doc'
    title = Column(String(500))
    content = Column(Text)
    sections = Column(JSON)  # List of sections with headings and content
    code_examples = Column(JSON)  # List of code blocks extracted
    doc_metadata = Column(JSON)  # Additional metadata like author, date, etc.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("idx_document_repo_type", "repository_id", "doc_type"),
        Index("idx_document_path", "path"),
    )


class ConfigurationEntry(Base):
    """Configuration entry from appsettings.json or similar config files."""
    
    __tablename__ = "configuration_entries"
    
    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), index=True)
    config_key = Column(String(500), nullable=False, index=True)  # e.g., "Database:ConnectionString"
    config_value = Column(Text)
    config_type = Column(String(50))  # "string", "number", "boolean", "object", "array"
    environment = Column(String(50), index=True)  # "development", "staging", "production", "default"
    is_secret = Column(Integer, default=0)  # Boolean stored as integer (0 or 1)
    file_path = Column(String(1000))
    line_number = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("idx_config_key", "config_key"),
        Index("idx_config_repo_env", "repository_id", "environment"),
        Index("idx_config_secret", "is_secret"),
    )


class Dependency(Base):
    """Package dependency from package.json, .csproj, etc."""
    
    __tablename__ = "dependencies"
    
    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), index=True)
    package_name = Column(String(255), nullable=False, index=True)
    package_version = Column(String(100))
    version_constraint = Column(String(100))
    dependency_type = Column(String(50), index=True)  # "nuget", "npm", "pip", "maven"
    is_dev_dependency = Column(Integer, default=0)  # Boolean stored as integer
    is_transitive = Column(Integer, default=0)  # Boolean stored as integer
    license = Column(String(100))
    file_path = Column(String(1000))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("idx_dep_package", "package_name"),
        Index("idx_dep_repo_type", "repository_id", "dependency_type"),
    )


class ProjectReference(Base):
    """Project reference from .csproj files."""
    
    __tablename__ = "project_references"
    
    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    source_project_path = Column(String(1000), nullable=False)
    target_project_path = Column(String(1000), nullable=False)
    reference_type = Column(String(50))  # "project", "package"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("idx_proj_ref_repo", "repository_id"),
        Index("idx_proj_ref_source", "source_project_path"),
    )


class Embedding(Base):
    """Vector embedding for semantic search."""

    __tablename__ = "embeddings"

    id = Column(Integer, primary_key=True)
    chunk_id = Column(Integer, ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol_id = Column(Integer, ForeignKey("symbols.id", ondelete="CASCADE"), index=True)
    model_name = Column(String(100), nullable=False)
    model_version = Column(String(50))
    dimension = Column(Integer, nullable=False)
    vector = Column(Vector(), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    chunk = relationship("Chunk", back_populates="embeddings")
    symbol = relationship("Symbol", back_populates="embeddings")

    __table_args__ = (
        Index("idx_embedding_chunk", "chunk_id"),
        Index("idx_embedding_symbol", "symbol_id"),
    )


class Job(Base):
    """Background job tracking."""

    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    job_type = Column(String(50), nullable=False, index=True)
    status = Column(value_enum(JobStatusEnum), default=JobStatusEnum.PENDING, nullable=False, index=True)
    celery_task_id = Column(String(255), unique=True, index=True)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    duration_seconds = Column(Integer)
    error_message = Column(Text)
    error_traceback = Column(Text)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    job_metadata = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    repository = relationship("Repository", back_populates="jobs")

    __table_args__ = (
        Index("idx_job_status_created", "status", "created_at"),
        Index("idx_job_type_status", "job_type", "status"),
    )


class Worker(Base):
    """Celery worker tracking."""

    __tablename__ = "workers"

    id = Column(String(255), primary_key=True)
    hostname = Column(String(255), nullable=False)
    status = Column(value_enum(WorkerStatusEnum), default=WorkerStatusEnum.UNKNOWN, nullable=False, index=True)
    current_job_id = Column(Integer, ForeignKey("jobs.id", ondelete="SET NULL"), index=True)
    last_heartbeat_at = Column(DateTime)
    queues = Column(JSON)
    started_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_worker_status_heartbeat", "status", "last_heartbeat_at"),
    )


class ModuleSummary(Base):
    """AI-generated summaries of code modules for quick understanding."""

    __tablename__ = "module_summaries"

    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    module_path = Column(String(1000), nullable=False)  # e.g., "src/api", "backend/auth"
    module_name = Column(String(255), nullable=False, index=True)  # e.g., "api", "auth"
    
    # Module identification
    module_type = Column(String(50), nullable=False, index=True)  # "python_package", "typescript_module", "directory"
    is_package = Column(Integer, default=0)  # 1 if has __init__.py, package.json, etc.
    
    # Summary content (AI-generated)
    summary = Column(Text, nullable=False)  # High-level overview
    purpose = Column(Text)  # What is this module for?
    key_components = Column(JSON)  # List of key classes/functions with brief descriptions
    dependencies = Column(JSON)  # Internal and external dependencies
    entry_points = Column(JSON)  # List of main entry point symbols
    
    # Statistics
    file_count = Column(Integer, default=0)
    symbol_count = Column(Integer, default=0)
    line_count = Column(Integer, default=0)
    complexity_score = Column(Integer)  # 1-10 scale
    
    # Metadata
    generated_by = Column(String(100))  # "openai:gpt-4", "anthropic:claude-3", etc.
    content_hash = Column(String(64))  # Hash of module content to detect changes
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    version = Column(Integer, default=1)  # Incremented when regenerated
    
    # Relationships
    repository = relationship("Repository", back_populates="module_summaries")
    
    __table_args__ = (
        Index("idx_module_repo_path", "repository_id", "module_path"),
        Index("idx_module_type", "module_type", "repository_id"),
        UniqueConstraint("repository_id", "module_path", name="uq_module_summary_repo_path"),
    )


class AuditLog(Base):
    """Audit log for security and compliance."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    event_type = Column(String(100), nullable=False, index=True)
    user_id = Column(String(255), index=True)
    resource_type = Column(String(100))
    resource_id = Column(Integer)
    action = Column(String(100), nullable=False)
    details = Column(JSON)
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("idx_audit_event_timestamp", "event_type", "timestamp"),
        Index("idx_audit_user_timestamp", "user_id", "timestamp"),
    )


class OutgoingApiCall(Base):
    """HTTP API calls made from code (frontend→backend or backend→backend)."""
    
    __tablename__ = "outgoing_api_calls"
    
    id = Column(Integer, primary_key=True)
    symbol_id = Column(Integer, ForeignKey("symbols.id", ondelete="CASCADE"), index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), index=True)
    
    # HTTP call details
    http_method = Column(String(10), nullable=False, index=True)  # GET, POST, PUT, DELETE, etc.
    url_pattern = Column(String(2000), nullable=False, index=True)  # /api/users/{id}
    call_type = Column(String(50), nullable=False, index=True)  # frontend_to_backend, backend_to_backend
    http_client_library = Column(String(100))  # fetch, axios, HttpClient, RestSharp, etc.
    
    # Context
    line_number = Column(Integer)
    is_dynamic_url = Column(Integer, default=0)  # Boolean: 1 if URL contains variables
    context_metadata = Column(JSON)  # headers, body structure, query params, etc.
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("idx_api_call_repo", "repository_id"),
        Index("idx_api_call_url", "url_pattern"),
        Index("idx_api_call_symbol", "symbol_id"),
        Index("idx_api_call_type", "call_type"),
        Index("idx_api_call_method", "http_method"),
    )


class PublishedEvent(Base):
    """Events/messages published to message queues or event buses."""
    
    __tablename__ = "published_events"
    
    id = Column(Integer, primary_key=True)
    symbol_id = Column(Integer, ForeignKey("symbols.id", ondelete="CASCADE"), index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), index=True)
    
    # Event details
    event_type_name = Column(String(500), nullable=False, index=True)  # UserCreatedEvent, OrderPlacedEvent
    messaging_library = Column(String(100), index=True)  # MassTransit, NServiceBus, Azure Service Bus, RabbitMQ
    
    # Routing information
    topic_name = Column(String(500))  # Topic or queue name
    exchange_name = Column(String(500))  # For RabbitMQ
    routing_key = Column(String(500))  # For RabbitMQ
    
    # Context
    line_number = Column(Integer)
    event_metadata = Column(JSON)  # Message structure, correlation ID patterns, etc.
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("idx_published_event_repo", "repository_id"),
        Index("idx_published_event_type", "event_type_name"),
        Index("idx_published_event_topic", "topic_name"),
        Index("idx_published_event_library", "messaging_library"),
    )


class EventSubscription(Base):
    """Event/message handlers and subscribers."""
    
    __tablename__ = "event_subscriptions"
    
    id = Column(Integer, primary_key=True)
    symbol_id = Column(Integer, ForeignKey("symbols.id", ondelete="CASCADE"), nullable=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), index=True)
    
    # Subscription details
    event_type_name = Column(String(500), nullable=False, index=True)  # Event/message type being consumed
    messaging_library = Column(String(100), index=True)  # MassTransit, NServiceBus, etc.
    queue_name = Column(String(500))  # Queue or subscription name
    subscription_pattern = Column(String(500))  # Topic pattern or filter
    
    # Context
    line_number = Column(Integer)
    handler_class_name = Column(String(500))  # Class implementing the handler
    handler_metadata = Column(JSON)  # Retry policies, error handling, etc.
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("idx_event_sub_repo", "repository_id"),
        Index("idx_event_sub_type", "event_type_name"),
        Index("idx_event_sub_queue", "queue_name"),
        Index("idx_event_sub_library", "messaging_library"),
        Index("idx_event_sub_symbol", "symbol_id"),
    )


class ApiEndpointLink(Base):
    """Links between outgoing API calls and their target backend endpoints."""
    
    __tablename__ = "api_endpoint_links"
    
    id = Column(Integer, primary_key=True)
    
    # Source (caller)
    outgoing_call_id = Column(Integer, ForeignKey("outgoing_api_calls.id", ondelete="CASCADE"), nullable=False, index=True)
    source_repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Target (endpoint)
    target_symbol_id = Column(Integer, ForeignKey("symbols.id", ondelete="SET NULL"), index=True)
    target_repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="SET NULL"), index=True)
    
    # Matching metadata
    match_confidence = Column(Integer, nullable=False)  # 0-100 (stored as integer for SQLite compatibility)
    match_method = Column(String(50), nullable=False, index=True)  # 'exact', 'fuzzy', 'gateway_resolved', 'pattern'
    match_metadata = Column(JSON)  # Details about how the match was made
    
    # Gateway routing (if applicable)
    gateway_repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="SET NULL"))
    gateway_route_pattern = Column(String(2000))  # Ocelot/Nginx route that was used
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("idx_api_link_outgoing", "outgoing_call_id"),
        Index("idx_api_link_target", "target_symbol_id"),
        Index("idx_api_link_source_repo", "source_repository_id"),
        Index("idx_api_link_target_repo", "target_repository_id"),
        Index("idx_api_link_confidence", "match_confidence"),
        Index("idx_api_link_method", "match_method"),
    )


class EventLink(Base):
    """Links between event publishers and subscribers."""
    
    __tablename__ = "event_links"
    
    id = Column(Integer, primary_key=True)
    
    # Publisher
    published_event_id = Column(Integer, ForeignKey("published_events.id", ondelete="CASCADE"), nullable=False, index=True)
    publisher_repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Subscriber
    event_subscription_id = Column(Integer, ForeignKey("event_subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    subscriber_repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Matching metadata
    match_confidence = Column(Integer, nullable=False)  # 0-100
    match_method = Column(String(50), nullable=False, index=True)  # 'exact_type', 'topic_match', 'routing_key'
    match_metadata = Column(JSON)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("idx_event_link_publisher", "published_event_id"),
        Index("idx_event_link_subscriber", "event_subscription_id"),
        Index("idx_event_link_pub_repo", "publisher_repository_id"),
        Index("idx_event_link_sub_repo", "subscriber_repository_id"),
        Index("idx_event_link_confidence", "match_confidence"),
    )


class GatewayRoute(Base):
    """Parsed gateway routing rules from Ocelot/Nginx configurations."""
    
    __tablename__ = "gateway_routes"
    
    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    file_path = Column(String(1000), nullable=False)  # Path to ocelot.json or nginx.conf
    
    # Gateway type
    gateway_type = Column(String(50), nullable=False, index=True)  # 'ocelot', 'nginx', 'kong', etc.
    
    # Route details
    downstream_path_template = Column(String(2000), index=True)  # Frontend-facing path
    upstream_path_template = Column(String(2000))    # Backend-facing path
    upstream_host = Column(String(500), index=True)  # Target service host
    upstream_port = Column(Integer)
    
    # HTTP methods
    http_methods = Column(JSON)  # ['GET', 'POST']
    
    # Additional metadata
    route_name = Column(String(500))
    priority = Column(Integer)
    route_metadata = Column(JSON)  # Rate limits, auth, transforms, etc.
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("idx_gateway_route_repo", "repository_id"),
        Index("idx_gateway_route_downstream", "downstream_path_template"),
        Index("idx_gateway_route_upstream_host", "upstream_host"),
        Index("idx_gateway_route_type", "gateway_type"),
        # Unique constraint to prevent duplicate routes
        # A route is unique per repository + file + downstream path + gateway type
        UniqueConstraint(
            "repository_id", "file_path", "downstream_path_template", "gateway_type",
            name="uq_gateway_route_repo_file_path_type"
        ),
    )


class DockerService(Base):
    """Docker service from docker-compose.yml files."""
    
    __tablename__ = "docker_services"
    
    id = Column(Integer, primary_key=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    file_path = Column(String(1000), nullable=False)  # Path to docker-compose.yml
    
    # Service details
    service_name = Column(String(255), nullable=False, index=True)
    image = Column(String(500))
    container_name = Column(String(255))
    
    # Build configuration
    build_context = Column(String(1000))  # Build context path
    dockerfile = Column(String(500))  # Dockerfile path
    build_args = Column(JSON)  # Build arguments
    
    # Network and ports
    ports = Column(JSON)  # [{"host": 8080, "container": 80, "protocol": "tcp"}]
    expose = Column(JSON)  # [80, 443]
    networks = Column(JSON)  # ["backend", "frontend"]
    
    # Dependencies
    depends_on = Column(JSON)  # ["postgres", "redis"]
    links = Column(JSON)  # ["db:database"]
    
    # Environment and volumes
    environment = Column(JSON)  # {"KEY": "value"}
    volumes = Column(JSON)  # [{"source": "/host", "target": "/container", "mode": "rw"}]
    
    # Runtime configuration
    command = Column(Text)  # Override command
    entrypoint = Column(Text)  # Override entrypoint
    working_dir = Column(String(1000))
    user = Column(String(100))
    restart = Column(String(50))  # "always", "on-failure", etc.
    
    # Health and labels
    healthcheck = Column(JSON)  # Healthcheck configuration
    labels = Column(JSON)  # Service labels
    
    # Metadata
    service_metadata = Column(JSON)  # Additional metadata (extra_hosts, etc.)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("idx_docker_service_repo", "repository_id"),
        Index("idx_docker_service_name", "service_name"),
        Index("idx_docker_service_image", "image"),
        # Unique constraint: one service name per file per repository
        UniqueConstraint(
            "repository_id", "file_path", "service_name",
            name="uq_docker_service_repo_file_name"
        ),
    )


class ServiceRepositoryMapping(Base):
    """Maps Docker service names to repositories for URL resolution."""
    
    __tablename__ = "service_repository_mappings"
    
    id = Column(Integer, primary_key=True)
    
    # Source service
    docker_service_id = Column(Integer, ForeignKey("docker_services.id", ondelete="CASCADE"), index=True)
    service_name = Column(String(255), nullable=False, index=True)  # Denormalized for quick lookup
    
    # Target repository
    target_repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Mapping metadata
    confidence = Column(Integer, nullable=False)  # 0-100
    mapping_method = Column(String(50), nullable=False, index=True)  # "exact_name", "image_match", "path_match", "manual"
    mapping_metadata = Column(JSON)  # Details about how the mapping was made
    
    # Manual override
    is_manual = Column(Integer, default=0)  # Boolean: 1 if manually set, 0 if auto-detected
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("idx_service_mapping_docker_service", "docker_service_id"),
        Index("idx_service_mapping_target_repo", "target_repository_id"),
        Index("idx_service_mapping_service_name", "service_name"),
        Index("idx_service_mapping_confidence", "confidence"),
        # Unique constraint: one mapping per service per target repository
        UniqueConstraint(
            "docker_service_id", "target_repository_id",
            name="uq_service_mapping_service_repo"
        ),
    )


