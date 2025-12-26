# MCP Tools Reference

This document details the **12 core tools** exposed by the Axon MCP Server. These tools allow AI assistants (like Claude, ChatGPT, and Cursor) to query, analyze, and understand the codebase.

---

## 🔍 Core Search Tools

### `search`
**Description**: The primary entry point for finding code. Performs a hybrid search (semantic vector search + keyword matching) to find relevant code symbols, functions, classes, or files.

**Parameters**:
- `query` (string, required): The search query (e.g., "how does authentication work", "UserService", "JWT validation").
- `limit` (int, default: 10): Maximum number of results to return.

**Example Usage**:
```json
{
  "query": "find authentication middleware",
  "limit": 5
}
```

---

### `get_symbol_details`
**Description**: Retrieves comprehensive details for a specific code symbol, including its signature, docstring, file location, and immediate relationships.

**Parameters**:
- `fully_qualified_name` (string, required): The unique identifier of the symbol (e.g., `Axon.Server.Services.UserService` or `src.api.auth.authenticate_user`).

**Example Usage**:
```json
{
  "fully_qualified_name": "Axon.Server.Services.UserService"
}
```

---

### `get_file_symbols`
**Description**: Lists all symbols (classes, functions, variables) defined within a specific file. Useful for understanding file structure.

**Parameters**:
- `file_path` (string, required): Relative path to the file (e.g., `src/services/user_service.py`).

**Example Usage**:
```json
{
  "file_path": "src/api/routes/auth.py"
}
```

---

## 📞 Relationships & Architecture

### `get_call_graph`
**Description**: Builds a call graph for a specific symbol to understand its dependencies (what it calls) and usages (what calls it).

**Parameters**:
- `symbol_name` (string, required): The name of the symbol to analyze.
- `direction` (string, default: "both"): Direction of analysis ("incoming", "outgoing", or "both").
- `depth` (int, default: 2): How deep to traverse the graph.

**Example Usage**:
```json
{
  "symbol_name": "ProcessOrder",
  "direction": "outgoing",
  "depth": 2
}
```

### `get_inheritance_hierarchy`
**Description**: Retrieves the inheritance tree for a class, showing parent classes and implemented interfaces.

**Parameters**:
- `class_name` (string, required): The name of the class to analyze.

**Example Usage**:
```json
{
  "class_name": "BaseController"
}
```

### `find_implementations`
**Description**: Finds all classes that implement a specific interface or inherit from a base class.

**Parameters**:
- `interface_name` (string, required): The name of the interface or base class.

**Example Usage**:
```json
{
  "interface_name": "IRepository"
}
```

---

## 🏗️ Structural Understanding

### `get_repository_structure`
**Description**: Returns a high-level overview of the repository structure, including solutions, projects, and key directories.

**Parameters**:
- `path` (string, optional): Subdirectory path to focus on.

**Example Usage**:
```json
{
  "path": "src"
}
```

### `get_module_summary`
**Description**: Retrieves an AI-generated summary of a specific module or directory, explaining its purpose and key components.

**Parameters**:
- `module_path` (string, required): Path to the module or directory.

**Example Usage**:
```json
{
  "module_path": "src/workers"
}
```

### `get_system_architecture_map`
**Description**: Generates a high-level architectural map of the system, showing services, layers, and major components.

**Parameters**: None

**Example Usage**:
```json
{}
```

---

## 🔎 Specialized Analysis

### `get_api_endpoints`
**Description**: Lists all detected REST API endpoints, including HTTP methods, routes, and associated handlers.

**Parameters**:
- `service_name` (string, optional): Filter by service name.

**Example Usage**:
```json
{}
```

### `explore_service`
**Description**: Provides a guided exploration of a specific service, listing its entry points, data models, and dependencies.

**Parameters**:
- `service_name` (string, required): The name of the service to explore.

**Example Usage**:
```json
{
  "service_name": "UserAPI"
}
```

### `get_ef_entities`
**Description**: Lists Entity Framework Core entities and their database mappings (tables, keys).

**Parameters**:
- `context_name` (string, optional): Filter by DbContext name.

**Example Usage**:
```json
{
  "context_name": "AppDbContext"
}
```
