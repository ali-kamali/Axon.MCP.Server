from enum import Enum


class LanguageEnum(str, Enum):
    """Programming language types."""

    CSHARP = "CSHARP"
    JAVASCRIPT = "JAVASCRIPT"
    TYPESCRIPT = "TYPESCRIPT"
    VUE = "VUE"
    PYTHON = "PYTHON"
    GO = "GO"
    JAVA = "JAVA"
    MARKDOWN = "MARKDOWN"
    SQL = "SQL"
    UNKNOWN = "UNKNOWN"


class SymbolKindEnum(str, Enum):
    """Types of code symbols."""

    FUNCTION = "FUNCTION"
    METHOD = "METHOD"
    CLASS = "CLASS"
    INTERFACE = "INTERFACE"
    STRUCT = "STRUCT"
    ENUM = "ENUM"
    VARIABLE = "VARIABLE"
    CONSTANT = "CONSTANT"
    PROPERTY = "PROPERTY"
    NAMESPACE = "NAMESPACE"
    MODULE = "MODULE"
    TYPE_ALIAS = "TYPE_ALIAS"  # TypeScript type aliases
    DOCUMENT_SECTION = "DOCUMENT_SECTION"  # Markdown headings
    CODE_EXAMPLE = "CODE_EXAMPLE"  # Code blocks in markdown
    ENDPOINT = "ENDPOINT"  # API endpoints (e.g. Express routes, Controllers)


class AccessModifierEnum(str, Enum):
    """Access modifiers."""

    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    PROTECTED = "PROTECTED"
    INTERNAL = "INTERNAL"
    PROTECTED_INTERNAL = "PROTECTED_INTERNAL"
    PRIVATE_PROTECTED = "PRIVATE_PROTECTED"


class RelationTypeEnum(str, Enum):
    """Types of symbol relationships."""

    CALLS = "CALLS"
    IMPORTS = "IMPORTS"
    EXPORTS = "EXPORTS"
    INHERITS = "INHERITS"
    IMPLEMENTS = "IMPLEMENTS"
    USES = "USES"
    CONTAINS = "CONTAINS"
    OVERRIDES = "OVERRIDES"
    REFERENCES = "REFERENCES"


class RepositoryStatusEnum(str, Enum):
    """Repository synchronization status."""

    PENDING = "PENDING"
    CLONING = "CLONING"
    PARSING = "PARSING"
    EXTRACTING = "EXTRACTING"
    EMBEDDING = "EMBEDDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class JobStatusEnum(str, Enum):
    """Background job status."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RETRYING = "RETRYING"


class WorkerStatusEnum(str, Enum):
    """Worker status."""

    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    BUSY = "BUSY"
    STARTING = "STARTING"
    UNKNOWN = "UNKNOWN"


class SourceControlProviderEnum(str, Enum):
    """Source control provider types."""

    GITLAB = "GITLAB"
    AZUREDEVOPS = "AZUREDEVOPS"


class MCPToolEnum(str, Enum):
    """MCP tool names."""

    SEARCH_CODE = "search_code"
    SEARCH_BY_PATH = "search_by_path"
    GET_FUNCTION_DETAILS = "get_function_details"
    GET_CLASS_DETAILS = "get_class_details"
    FIND_DEPENDENCIES = "find_dependencies"
    LIST_REPOSITORIES = "list_repositories"
    GET_FILE_CONTENT = "get_file_content"
    GET_SYMBOL_CONTEXT = "get_symbol_context"
    SEARCH_DOCUMENTATION = "search_documentation"
    SEARCH_CONFIGURATION = "search_configuration"
    LIST_DEPENDENCIES = "list_dependencies"
    FIND_API_ENDPOINTS = "find_api_endpoints"
    FIND_USAGES = "find_usages"
    FIND_IMPLEMENTATIONS = "find_implementations"
    FIND_REFERENCES = "find_references"
    GET_FILE_TREE = "get_file_tree"
    LIST_SYMBOLS_IN_FILE = "list_symbols_in_file"
    GET_CALL_HIERARCHY = "get_call_hierarchy"
    FIND_CALLERS = "find_callers"
    FIND_CALLEES = "find_callees"
    ANALYZE_ARCHITECTURE = "analyze_architecture"
    TRACE_REQUEST_FLOW = "trace_request_flow"
    GET_PROJECT_MAP = "get_project_map"
    GET_MODULE_SUMMARY = "get_module_summary"
    QUERY_CODEBASE_STRUCTURE = "query_codebase_structure"  # Service-Related Tools
    LIST_SERVICES = "list_services"
    GET_SERVICE_DETAILS = "get_service_details"
    GET_SERVICE_DOCUMENTATION = "get_service_documentation"
    GET_DB_ENTITY_MAPPING = "get_db_entity_mapping"
    LIST_EF_ENTITIES = "list_ef_entities"
    GET_SYSTEM_MAP = "get_system_map"
