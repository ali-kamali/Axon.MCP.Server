"""Tool definitions for MCP server."""

from mcp.types import Tool
from src.config.enums import MCPToolEnum

# Define all MCP tools
TOOLS = [
    Tool(
        name=MCPToolEnum.SEARCH_CODE.value,
        description="Search for code symbols across repositories using semantic search",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (function name, class name, or description)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 10, max: 50)",
                    "default": 10
                },
                "repository_name": {
                    "type": "string",
                    "description": "Filter by repository name"
                },
                "language": {
                    "type": "string",
                    "description": "Filter by programming language (csharp, javascript, typescript, vue)"
                },
                "symbol_kind": {
                    "type": "string",
                    "description": "Filter by symbol kind (function, class, method, etc.)"
                }
            },
            "required": ["query"]
        }
    ),
    Tool(
        name=MCPToolEnum.GET_SYMBOL_CONTEXT.value,
        description="Get detailed context for a specific symbol with optional call graph traversal",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol_id": {
                    "type": "integer",
                    "description": "ID of the symbol"
                },
                "include_relationships": {
                    "type": "boolean",
                    "description": "Include direct relationships",
                    "default": True
                },
                "depth": {
                    "type": "integer",
                    "description": "Traversal depth (0=no traversal, 1=direct, 2+=recursive, max: 5)",
                    "default": 0
                },
                "direction": {
                    "type": "string",
                    "description": "Traversal direction: 'downstream', 'upstream', or 'both'",
                    "default": "downstream"
                },
                "max_symbols": {
                    "type": "integer",
                    "description": "Maximum symbols to include (1-100)",
                    "default": 50
                },
                "relation_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Relationship types to follow (CALLS, INHERITS, IMPLEMENTS, USES)"
                }
            },
            "required": ["symbol_id"]
        }
    ),
    Tool(
        name=MCPToolEnum.LIST_REPOSITORIES.value,
        description="List available repositories with their status and statistics",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of repositories to return",
                    "default": 20
                }
            }
        }
    ),
    Tool(
        name=MCPToolEnum.SEARCH_DOCUMENTATION.value,
        description="Search markdown documentation files",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "repository_id": {
                    "type": "integer",
                    "description": "Optional repository ID filter"
                },
                "doc_type": {
                    "type": "string",
                    "description": "Optional document type filter"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    ),
    Tool(
        name=MCPToolEnum.SEARCH_CONFIGURATION.value,
        description="Search configuration settings",
        inputSchema={
            "type": "object",
            "properties": {
                "key_pattern": {
                    "type": "string",
                    "description": "Configuration key pattern (supports wildcards like 'Database:*')"
                },
                "repository_id": {
                    "type": "integer",
                    "description": "Optional repository ID filter"
                },
                "environment": {
                    "type": "string",
                    "description": "Optional environment filter"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 20
                }
            },
            "required": ["key_pattern"]
        }
    ),
    Tool(
        name=MCPToolEnum.LIST_DEPENDENCIES.value,
        description="List package dependencies",
        inputSchema={
            "type": "object",
            "properties": {
                "repository_id": {
                    "type": "integer",
                    "description": "Repository ID"
                },
                "dependency_type": {
                    "type": "string",
                    "description": "Optional type filter (nuget, npm, etc.)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 50
                }
            },
            "required": ["repository_id"]
        }
    ),
    Tool(
        name=MCPToolEnum.GET_FILE_CONTENT.value,
        description="Read file content with line numbers",
        inputSchema={
            "type": "object",
            "properties": {
                "repository_id": {
                    "type": "integer",
                    "description": "Repository ID"
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to file within repository"
                },
                "start_line": {
                    "type": "integer",
                    "description": "Optional start line (1-indexed)"
                },
                "end_line": {
                    "type": "integer",
                    "description": "Optional end line (1-indexed)"
                }
            },
            "required": ["repository_id", "file_path"]
        }
    ),
    Tool(
        name=MCPToolEnum.FIND_USAGES.value,
        description="Find all places where a symbol is used",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol_id": {
                    "type": "integer",
                    "description": "Symbol ID to find usages for"
                },
                "relationship_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional filter by relationship types (e.g., ['CALLS', 'USES'])"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 50
                }
            },
            "required": ["symbol_id"]
        }
    ),
    Tool(
        name=MCPToolEnum.FIND_IMPLEMENTATIONS.value,
        description=(
            "Find all classes that implement an interface. "
            "⚠️ IMPORTANT: This tool ONLY works for INTERFACE symbols. "
            "It will return an error if you pass a class, method, or other symbol type. "
            "To find what a class inherits from, use get_symbol_context with include_relationships=true."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "interface_id": {
                    "type": "integer",
                    "description": "Interface symbol ID (must be an INTERFACE, not a CLASS or METHOD)"
                }
            },
            "required": ["interface_id"]
        }
    ),
    Tool(
        name=MCPToolEnum.FIND_REFERENCES.value,
        description="Find all references to a symbol",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol_id": {
                    "type": "integer",
                    "description": "Symbol ID"
                },
                "reference_type": {
                    "type": "string",
                    "description": "Optional filter by type (single)"
                },
                "relationship_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional filter by relationship types (list)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 50
                }
            },
            "required": ["symbol_id"]
        }
    ),
    Tool(
        name=MCPToolEnum.GET_FILE_TREE.value,
        description="Get directory tree structure",
        inputSchema={
            "type": "object",
            "properties": {
                "repository_id": {
                    "type": "integer",
                    "description": "Repository ID"
                },
                "path": {
                    "type": "string",
                    "description": "Optional path to start from",
                    "default": ""
                },
                "depth": {
                    "type": "integer",
                    "description": "Maximum depth to traverse",
                    "default": 3
                }
            },
            "required": ["repository_id"]
        }
    ),
    Tool(
        name=MCPToolEnum.LIST_SYMBOLS_IN_FILE.value,
        description="List all symbols in a specific file",
        inputSchema={
            "type": "object",
            "properties": {
                "repository_id": {
                    "type": "integer",
                    "description": "Repository ID"
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to file"
                },
                "symbol_kinds": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional filter by kinds"
                }
            },
            "required": ["repository_id", "file_path"]
        }
    ),
    Tool(
        name=MCPToolEnum.FIND_API_ENDPOINTS.value,
        description="Find all API endpoints in repository",
        inputSchema={
            "type": "object",
            "properties": {
                "repository_id": {
                    "type": "integer",
                    "description": "Repository ID"
                },
                "http_method": {
                    "type": "string",
                    "description": "Optional HTTP method filter"
                },
                "route_pattern": {
                    "type": "string",
                    "description": "Optional route pattern filter"
                }
            },
            "required": ["repository_id"]
        }
    ),
    Tool(
        name=MCPToolEnum.GET_CALL_HIERARCHY.value,
        description="Get call hierarchy tree",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol_id": {
                    "type": "integer",
                    "description": "Symbol ID"
                },
                "direction": {
                    "type": "string",
                    "description": "'outbound' (callees) or 'inbound' (callers)",
                    "default": "outbound"
                },
                "depth": {
                    "type": "integer",
                    "description": "Maximum depth",
                    "default": 3
                }
            },
            "required": ["symbol_id"]
        }
    ),
    Tool(
        name=MCPToolEnum.FIND_CALLERS.value,
        description="Find all symbols that call this one",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol_id": {
                    "type": "integer",
                    "description": "Symbol ID"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 50
                }
            },
            "required": ["symbol_id"]
        }
    ),
    Tool(
        name=MCPToolEnum.FIND_CALLEES.value,
        description="Find all functions/methods that this symbol calls",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol_id": {
                    "type": "integer",
                    "description": "Symbol ID"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 50
                }
            },
            "required": ["symbol_id"]
        }
    ),
    Tool(
        name=MCPToolEnum.ANALYZE_ARCHITECTURE.value,
        description="Analyze repository architecture and detect patterns",
        inputSchema={
            "type": "object",
            "properties": {
                "repository_id": {
                    "type": "integer",
                    "description": "Repository ID"
                }
            },
            "required": ["repository_id"]
        }
    ),
    Tool(
        name=MCPToolEnum.SEARCH_BY_PATH.value,
        description="Search for files by path pattern",
        inputSchema={
            "type": "object",
            "properties": {
                "repository_id": {
                    "type": "integer",
                    "description": "Repository ID"
                },
                "path_pattern": {
                    "type": "string",
                    "description": "Path pattern with wildcards (e.g., '*/services/*.cs')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 50
                }
            },
            "required": ["repository_id", "path_pattern"]
        }
    ),
    Tool(
        name=MCPToolEnum.TRACE_REQUEST_FLOW.value,
        description="Trace request flow through application layers with layer detection and configurable depth",
        inputSchema={
            "type": "object",
            "properties": {
                "endpoint": {
                    "type": "string",
                    "description": "API endpoint (e.g., 'POST /api/users')"
                },
                "repository_id": {
                    "type": "integer",
                    "description": "Repository ID"
                },
                "depth": {
                    "type": "integer",
                    "description": "Maximum traversal depth (default: 5, max: 10)",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 10
                }
            },
            "required": ["endpoint", "repository_id"]
        }
    ),
    Tool(
        name=MCPToolEnum.GET_PROJECT_MAP.value,
        description="Get high-level project map showing modules and their relationships",
        inputSchema={
            "type": "object",
            "properties": {
                "repository_id": {
                    "type": "integer",
                    "description": "Repository ID"
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum depth for module mapping",
                    "default": 2
                }
            },
            "required": ["repository_id"]
        }
    ),
    Tool(
        name=MCPToolEnum.GET_MODULE_SUMMARY.value,
        description="Get AI-generated summary for a specific module",
        inputSchema={
            "type": "object",
            "properties": {
                "repository_id": {
                    "type": "integer",
                    "description": "Repository ID"
                },
                "module_path": {
                    "type": "string",
                    "description": "Path to module (e.g., 'src/api', 'backend/auth')"
                },
                "generate_if_missing": {
                    "type": "boolean",
                    "description": "Generate summary if it doesn't exist",
                    "default": True
                }
            },
            "required": ["repository_id", "module_path"]
        }
    ),
    Tool(
        name=MCPToolEnum.QUERY_CODEBASE_STRUCTURE.value,
        description="Query codebase structure using natural language (Text-to-SQL)",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query (e.g., 'Find all public methods in controllers')"
                },
                "repository_id": {
                    "type": "integer",
                    "description": "Optional repository filter"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 50
                }
            },
            "required": ["query"]
        }
    ),
    Tool(
        name=MCPToolEnum.LIST_SERVICES.value,
        description="List detected services in the codebase with hierarchical grouping",
        inputSchema={
            "type": "object",
            "properties": {
                "repository_id": {
                    "type": "integer",
                    "description": "Optional repository ID filter"
                },
                "service_type": {
                    "type": "string",
                    "description": "Optional service type filter (API, Worker, Console, Library)"
                }
            }
        }
    ),
    Tool(
        name=MCPToolEnum.GET_SERVICE_DETAILS.value,
        description="Get detailed information about a specific service",
        inputSchema={
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Name of the service"
                }
            },
            "required": ["service_name"]
        }
    ),
    Tool(
        name=MCPToolEnum.GET_SERVICE_DOCUMENTATION.value,
        description="Get comprehensive markdown documentation for a service",
        inputSchema={
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Name of the service"
                }
            },
            "required": ["service_name"]
        }
    ),
    Tool(
        name=MCPToolEnum.LIST_EF_ENTITIES.value,
        description="List all EF Core entities in a repository",
        inputSchema={
            "type": "object",
            "properties": {
                "repository_id": {
                    "type": "integer",
                    "description": "Repository ID"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of entities to return",
                    "default": 50
                }
            },
            "required": ["repository_id"]
        }
    ),
    Tool(
        name=MCPToolEnum.GET_DB_ENTITY_MAPPING.value,
        description="Get database entity mapping for a specific EF Core entity",
        inputSchema={
            "type": "object",
            "properties": {
                "repository_id": {
                    "type": "integer",
                    "description": "Repository ID"
                },
                "entity_name": {
                    "type": "string",
                    "description": "Entity class name (e.g., 'Order')"
                }
            },
            "required": ["repository_id", "entity_name"]
        }
    ),
    Tool(
        name=MCPToolEnum.GET_SYSTEM_MAP.value,
        description="Get high-level system context map and architecture overview",
        inputSchema={
            "type": "object",
            "properties": {
                "repository_id": {
                    "type": "integer",
                    "description": "Optional repository ID to focus on. If omitted, returns global system context."
                }
            }
        }
    ),
]
