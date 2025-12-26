# Development Guide

## Setup Development Environment

```bash
# Clone and install
git clone https://github.com/ali-kamali/Axon.MCP.Server.git
cd axon.mcp.server
make dev-install

# Install pre-commit hooks
pre-commit install
```

## Code Standards

This project follows strict coding standards:
- **Enums**: Use enums instead of direct string usage
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes
- **CSS**: Use `snake_case` for CSS class names
- **No Inline Styles**: Always use CSS classes
- **Type Hints**: Required for all function signatures
- **Documentation**: Docstrings for all public APIs

## Available Commands

```bash
# Development
make dev-install        # Install development dependencies
make format             # Format code with black and isort
make lint               # Run linters (flake8, mypy, pylint)
make test               # Run tests with coverage

# Database
make migrate            # Run database migrations
make seed               # Seed test data

# Docker
make docker-up          # Start all services
make docker-down        # Stop all services

# Cleanup
make clean              # Clean cache and build files
```

## Testing

### Run All Tests

```bash
# Run all tests with coverage
make test

# Run specific test suite
pytest tests/unit/test_parsers.py -v

# Run tests with specific marker
pytest -m integration

# Run tests in parallel
pytest -n auto
```

### Test Coverage

```bash
# Generate coverage report
pytest --cov=src --cov-report=html --cov-report=term

# View HTML report
open htmlcov/index.html
```

### Testing Strategy

- **Unit Tests**: 85%+ coverage for all components
- **Integration Tests**: End-to-end workflow validation
- **Performance Tests**: Load testing and benchmarks
- **Security Tests**: Automated security scanning

## How to Add a New Feature

### 1. Adding a New MCP Tool

To add a new tool for AI assistants (e.g., `analyze_complexity`):

1.  **Define the Tool Logic**:
    Add the implementation method in `src/mcp_server/server.py` (or delegate to a service).
    ```python
    async def _analyze_complexity(self, repository_id: int, file_path: str) -> str:
        # Implementation logic
        return "Complexity analysis result"
    ```

2.  **Register the Tool**:
    Add the tool definition to the `list_tools` function in `src/mcp_server/server.py`.
    ```python
    Tool(
        name="analyze_complexity",
        description="Analyze the cyclomatic complexity of a file",
        inputSchema={
            "type": "object",
            "properties": {
                "repository_id": {"type": "integer"},
                "file_path": {"type": "string"}
            },
            "required": ["repository_id", "file_path"]
        }
    )
    ```

3.  **Add Dispatch Logic**:
    Update the `call_tool` function in `src/mcp_server/server.py` to handle the new tool name.
    ```python
    elif name == "analyze_complexity":
        return await _analyze_complexity(...)
    ```

4.  **Update Documentation**:
    Add the new tool to `docs/api/mcp_tools.md`.

### 2. Adding a New API Endpoint

To add a new REST endpoint (e.g., `GET /api/v1/stats`):

1.  **Create the Router**:
    Create a new file `src/api/routes/stats.py`.
    ```python
    from fastapi import APIRouter
    router = APIRouter()

    @router.get("/stats")
    async def get_stats():
        return {"status": "ok"}
    ```

2.  **Register the Router**:
    Import and include the router in `src/api/main.py`.
    ```python
    from src.api.routes.stats import router as stats_router
    app.include_router(stats_router, prefix="/api/v1", tags=["Stats"])
    ```

### 3. Adding a New Language Parser

To support a new language (e.g., Python):

1.  **Create the Parser Class**:
    Create `src/parsers/python_parser.py` inheriting from `BaseParser`.
    ```python
    from src.parsers.base_parser import BaseParser

    class PythonParser(BaseParser):
        def parse(self, file_path: str, content: str):
            # Tree-sitter parsing logic
            pass
    ```

2.  **Register the Parser**:
    Update `src/extractors/knowledge_extractor.py` to instantiate `PythonParser` for `.py` files.

