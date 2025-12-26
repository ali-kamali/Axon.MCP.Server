# Axon MCP Server

## Overview

The Axon MCP (Model Context Protocol) Server enables ChatGPT and other AI assistants to interact with your code repositories through a standardized protocol. It exposes powerful tools for searching code, inspecting symbols, and exploring repositories using hybrid search (keyword + semantic).

## Features

- **Hybrid Search**: Combines keyword and semantic search for better results
- **Symbol Context**: Detailed information about functions, classes, and other code symbols
- **Repository Management**: List and filter repositories
- **Real-time Metrics**: Prometheus metrics for monitoring
- **Comprehensive Logging**: Structured logging for debugging

## Architecture

The MCP server is built using the [MCP Python SDK](https://modelcontextprotocol.io/), implementing the Model Context Protocol specification. It uses:

- **AxonMCPServer**: Class-based server wrapper around `mcp.server.Server`
- **Network transport**: TCP/IP communication (configurable host/port)
- **SearchService**: Hybrid search with keyword + semantic capabilities
- **PostgreSQL + pgvector**: Vector similarity search for semantic matching
- **Prometheus**: Metrics collection for monitoring

## Available Tools

### 1. search_code

Search for code symbols across repositories using hybrid search.

**Parameters:**
- `query` (string, required): Search query (function name, class name, or description)
- `limit` (int, optional): Maximum number of results (default: 10, max: 50)
- `repository_name` (string, optional): Filter by repository name
- `language` (string, optional): Filter by programming language (csharp, javascript, typescript, vue, python)
- `symbol_kind` (string, optional): Filter by symbol kind (function, class, method, interface, etc.)

**Example:**
```json
{
  "query": "authenticate user",
  "limit": 10,
  "language": "csharp",
  "symbol_kind": "method"
}
```

**Returns:**
Formatted markdown text with search results including:
- Symbol name and kind
- Repository and file location
- Line numbers
- Function signature
- Documentation
- Relevance score

### 2. get_symbol_context

Get detailed context for a specific symbol including relationships.

**Parameters:**
- `symbol_id` (int, required): ID of the symbol
- `include_relationships` (bool, optional): Include related symbols (default: true)

**Example:**
```json
{
  "symbol_id": 123,
  "include_relationships": true
}
```

**Returns:**
Formatted markdown text with:
- Symbol details (name, kind, signature)
- Location information (repository, file, lines)
- Documentation
- Parameters and return type
- Complexity metrics
- Access modifiers
- Relationships (calls, inheritance, etc.)

### 3. list_repositories

List available repositories with their status and statistics.

**Parameters:**
- `limit` (int, optional): Maximum number of repositories to return (default: 20)

**Example:**
```json
{
  "limit": 20
}
```

**Returns:**
Formatted markdown text with:
- Repository name
- Status (completed, parsing, failed, etc.)
- Number of files
- Number of symbols
- Last sync timestamp

## Running the MCP Server

### Using Makefile (Recommended)

```bash
# Start MCP server (recommended)
make mcp-start

# Start in development mode
make mcp-dev
```

### Using Python Module

```bash
# Recommended: Run as a module
python -m src.mcp_server

# Alternative: Run main.py directly
python src/mcp_server/main.py
```

### Using Python API

```python
import asyncio
from src.config.settings import settings
from src.mcp_server.server import AxonMCPServer

# Create and start the server
server = AxonMCPServer()
asyncio.run(server.start(host=settings.mcp_server_host, port=settings.mcp_server_port))
```

## Configuration

The MCP server uses the same configuration as the main application. Key settings:

```env
# Database (required)
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/axon

# Redis (required)
REDIS_URL=redis://localhost:6379/0

# Embeddings (required for semantic search)
EMBEDDING_PROVIDER=local  # or "openai"
LOCAL_EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2

# Optional: OpenAI embeddings
OPENAI_API_KEY=sk-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Metrics
METRICS_ENABLED=true
```

## ChatGPT Integration

### Using Stdio Transport (Local)

For local connections, use stdio transport:

1. **Start the server:**
   ```bash
   make mcp-start
   ```

2. **Configure ChatGPT/Cursor:**
   Add the MCP server configuration to your settings:
   ```json
   {
     "mcpServers": {
       "axon": {
         "command": "python",
         "args": ["-m", "src.mcp_server"],
         "cwd": "/path/to/Axon.MCP.Server"
       }
     }
   }
   ```

3. **Use the tools:**
   ChatGPT/Cursor will now have access to the three MCP tools for searching and exploring your code.

### Using HTTP Transport (Remote)

For remote connections, use HTTP transport:

1. **Configure the server:**
   Set in your `.env` file:
   ```env
   MCP_TRANSPORT=http
   MCP_HTTP_HOST=0.0.0.0
   MCP_HTTP_PORT=8001
   MCP_HTTP_PATH=/mcp
   ```

2. **Start the API server:**
   The MCP HTTP endpoint is available at `/mcp` when the FastAPI server is running:
   ```bash
   # Start the API server (includes MCP HTTP endpoint)
   uvicorn src.api.main:app --host 0.0.0.0 --port 8080
   ```

3. **Configure Cursor/Client:**
   ```json
   {
     "mcpServers": {
       "axon-remote": {
         "url": "http://your-remote-server.com:8080/mcp"
       }
     }
   }
   ```

   Or if your client supports it:
   ```json
   {
     "mcpServers": {
       "axon-remote": {
         "transport": "http",
         "url": "http://your-remote-server.com:8080/mcp"
       }
     }
   }
   ```

4. **Use the tools:**
   Your client will now connect to the remote MCP server over HTTP.

## Testing

### Run Integration Tests

```bash
# Run all tests
pytest tests/integration/test_mcp_server.py -v

# Run specific test
pytest tests/integration/test_mcp_server.py::TestMCPServer::test_search_code_tool_basic -v

# Run with coverage
pytest tests/integration/test_mcp_server.py --cov=src.mcp_server --cov-report=html
```

### Manual Testing

You can test the MCP server manually using the MCP Inspector:

```bash
# Install MCP Inspector
npm install -g @modelcontextprotocol/inspector

# Run inspector with your server
mcp-inspector python -m src.mcp_server
```

## Monitoring

### Metrics

The MCP server exposes Prometheus metrics:

```
# Tool calls
mcp_tool_calls_total{tool_name="search_code", status="success"} 42
mcp_tool_calls_total{tool_name="get_symbol_context", status="success"} 15
mcp_tool_calls_total{tool_name="list_repositories", status="success"} 8

# Tool duration
mcp_tool_duration_seconds{tool_name="search_code"} 0.234
mcp_tool_duration_seconds{tool_name="get_symbol_context"} 0.089
mcp_tool_duration_seconds{tool_name="list_repositories"} 0.045
```

### Logging

Structured logs are written to stdout in JSON format:

```json
{
  "timestamp": "2024-01-15T10:30:45Z",
  "level": "INFO",
  "event": "mcp_search_completed",
  "query": "authenticate user",
  "result_count": 5,
  "duration_ms": 234
}
```

## Performance

Target performance metrics:

- **Tool response time**: < 500ms
- **Concurrent requests**: 10+ simultaneous tool calls
- **Memory usage**: < 500MB
- **No connection leaks**: Proper session management

## Troubleshooting

### Common Issues

1. **"Database connection failed"**
   - Ensure PostgreSQL is running
   - Check DATABASE_URL in .env
   - Verify database migrations are up to date

2. **"Embedding generation failed"**
   - Check EMBEDDING_PROVIDER setting
   - For OpenAI: verify OPENAI_API_KEY
   - For local: ensure model is downloaded

3. **"No results found"**
   - Verify repositories are synced
   - Check embeddings are generated
   - Try simpler search queries

4. **"Import errors"**
   - Install dependencies: `pip install -r requirements.txt`
   - Activate virtual environment

### Debug Mode

Enable debug logging:

```bash
LOG_LEVEL=DEBUG python -m src.mcp_server
```

## Development

### Adding New Tools

1. Create a new tool function in `server.py`:
   ```python
   @mcp.tool(name="my_new_tool")
   async def my_new_tool(param1: str, param2: int) -> str:
       """Tool description for ChatGPT."""
       # Implementation
       return formatted_result
   ```

2. Add tool name to `MCPToolEnum` in `src/config/enums.py`

3. Add tests to `tests/integration/test_mcp_server.py`

### Code Style

Follow the project's code style:
- Use functional programming approach
- Add type hints
- Write comprehensive docstrings
- Add logging and metrics
- Handle errors gracefully

## Related Documentation

- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Task 11 Implementation Guide](../../docs/TASK_11_MCP_Server.md)
- [API Quick Reference](../../docs/API_QUICK_REFERENCE.md)

## License

See main project LICENSE file.

