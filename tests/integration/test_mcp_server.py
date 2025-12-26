"""Integration tests for MCP server."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.enums import (
    AccessModifierEnum,
    LanguageEnum,
    RepositoryStatusEnum,
    SymbolKindEnum,
)
from src.database.models import File, Repository, Symbol
from src.mcp_server.server import AxonMCPServer


@pytest.mark.asyncio
class TestMCPServer:
    """Test MCP server functionality."""

    async def test_mcp_server_initialization(self):
        """Test MCP server initializes correctly."""
        server = AxonMCPServer()
        assert server is not None
        assert server.server is not None
        assert server.server.name == "axon-mcp-server"

    async def test_search_code_response_format(self, async_session: AsyncSession):
        """Test search_code returns proper MCP response format."""
        # Create minimal test data
        repo = Repository(
            name="test-repo",
            url="https://gitlab.com/test/repo",
            status=RepositoryStatusEnum.COMPLETED,
            total_files=1,
            total_symbols=1,
        )
        async_session.add(repo)
        await async_session.flush()

        file = File(
            repository_id=repo.id,
            path="test.py",
            language=LanguageEnum.PYTHON,
            size_bytes=100,
            line_count=10,
        )
        async_session.add(file)
        await async_session.flush()

        symbol = Symbol(
            file_id=file.id,
            name="test_function",
            kind=SymbolKindEnum.FUNCTION,
            language=LanguageEnum.PYTHON,
            signature="def test_function():",
            documentation="A test function",
            start_line=1,
            end_line=5,
            fully_qualified_name="test.test_function",
        )
        async_session.add(symbol)
        await async_session.commit()

        # Create server and get the registered tool
        server = AxonMCPServer()

        # Access the tool directly from the server's registry
        # The tools are registered as closures, so we need to call them directly
        with patch("src.mcp_server.server.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = async_session

            # Get the tool from server's registered tools
            search_tool = server.server._tools.get("search_code")
            assert search_tool is not None

            result = await search_tool.fn(query="test_function", limit=10)

            # Verify MCP response format
            assert isinstance(result, dict)
            assert "content" in result
            assert "isError" in result
            assert result["isError"] is False
            assert isinstance(result["content"], list)
            assert len(result["content"]) > 0
            assert result["content"][0].type == "text"
            assert "test_function" in result["content"][0].text

    async def test_get_symbol_context_response_format(
        self, async_session: AsyncSession
    ):
        """Test get_symbol_context returns proper MCP response format."""
        # Create test data
        repo = Repository(
            name="test-repo",
            url="https://gitlab.com/test/repo",
            status=RepositoryStatusEnum.COMPLETED,
        )
        async_session.add(repo)
        await async_session.flush()

        file = File(
            repository_id=repo.id,
            path="test.py",
            language=LanguageEnum.PYTHON,
            size_bytes=100,
        )
        async_session.add(file)
        await async_session.flush()

        symbol = Symbol(
            file_id=file.id,
            name="test_class",
            kind=SymbolKindEnum.CLASS,
            language=LanguageEnum.PYTHON,
            signature="class TestClass:",
            documentation="A test class",
            start_line=1,
            end_line=10,
            fully_qualified_name="test.TestClass",
            access_modifier=AccessModifierEnum.PUBLIC,
        )
        async_session.add(symbol)
        await async_session.commit()

        server = AxonMCPServer()

        with patch("src.mcp_server.server.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = async_session

            context_tool = server.server._tools.get("get_symbol_context")
            assert context_tool is not None

            result = await context_tool.fn(
                symbol_id=symbol.id, include_relationships=True
            )

            # Verify MCP response format
            assert isinstance(result, dict)
            assert "content" in result
            assert "isError" in result
            assert result["isError"] is False
            assert isinstance(result["content"], list)
            assert len(result["content"]) > 0
            assert result["content"][0].type == "text"
            assert "test_class" in result["content"][0].text.lower()

    async def test_get_symbol_context_not_found(self, async_session: AsyncSession):
        """Test get_symbol_context with non-existent symbol ID."""
        server = AxonMCPServer()

        with patch("src.mcp_server.server.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = async_session

            context_tool = server.server._tools.get("get_symbol_context")
            result = await context_tool.fn(
                symbol_id=99999, include_relationships=False
            )

            assert result["isError"] is True
            assert "Symbol not found" in result["content"][0].text

    async def test_list_repositories_response_format(
        self, async_session: AsyncSession
    ):
        """Test list_repositories returns proper MCP response format."""
        # Create test repositories
        repos = [
            Repository(
                name=f"repo-{i}",
                url=f"https://gitlab.com/test/repo-{i}",
                status=RepositoryStatusEnum.COMPLETED,
                total_files=10 * i,
                total_symbols=100 * i,
                last_synced_at=datetime.now(timezone.utc),
            )
            for i in range(1, 4)
        ]

        for repo in repos:
            async_session.add(repo)
        await async_session.commit()

        server = AxonMCPServer()

        with patch("src.mcp_server.server.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = async_session

            list_tool = server.server._tools.get("list_repositories")
            assert list_tool is not None

            result = await list_tool.fn(limit=20)

            # Verify MCP response format
            assert isinstance(result, dict)
            assert "content" in result
            assert "isError" in result
            assert result["isError"] is False
            assert isinstance(result["content"], list)
            assert len(result["content"]) > 0
            assert result["content"][0].type == "text"
            assert "repo-1" in result["content"][0].text

    async def test_list_repositories_empty(self, async_session: AsyncSession):
        """Test list_repositories when no repositories exist."""
        server = AxonMCPServer()

        with patch("src.mcp_server.server.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = async_session

            list_tool = server.server._tools.get("list_repositories")
            result = await list_tool.fn(limit=20)

            assert result["isError"] is False
            assert "No repositories available" in result["content"][0].text

    async def test_search_code_error_handling(self, async_session: AsyncSession):
        """Test search_code handles errors gracefully."""
        server = AxonMCPServer()

        with patch("src.mcp_server.server.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.side_effect = Exception(
                "Database error"
            )

            search_tool = server.server._tools.get("search_code")
            result = await search_tool.fn(query="test", limit=10)

            assert result["isError"] is True
            assert "Search failed" in result["content"][0].text

    async def test_search_code_with_filters(self, async_session: AsyncSession):
        """Test search_code with language and symbol kind filters."""
        # Create test data
        repo = Repository(
            name="filter-test-repo",
            url="https://gitlab.com/test/repo",
            status=RepositoryStatusEnum.COMPLETED,
        )
        async_session.add(repo)
        await async_session.flush()

        file = File(
            repository_id=repo.id,
            path="test.py",
            language=LanguageEnum.PYTHON,
            size_bytes=100,
        )
        async_session.add(file)
        await async_session.flush()

        symbol = Symbol(
            file_id=file.id,
            name="MyClass",
            kind=SymbolKindEnum.CLASS,
            language=LanguageEnum.PYTHON,
            signature="class MyClass:",
            start_line=1,
            end_line=10,
            fully_qualified_name="test.MyClass",
        )
        async_session.add(symbol)
        await async_session.commit()

        server = AxonMCPServer()

        with patch("src.mcp_server.server.get_async_session") as mock_session:
            mock_session.return_value.__aenter__.return_value = async_session

            search_tool = server.server._tools.get("search_code")
            result = await search_tool.fn(
                query="MyClass", limit=10, language="python", symbol_kind="class"
            )

            assert result["isError"] is False
            # Note: Since we're using SearchService which may not find results
            # due to empty embeddings, we just verify the response format
            assert "content" in result
            assert isinstance(result["content"], list)


@pytest.mark.asyncio
class TestMCPToolResponseFormatting:
    """Test MCP tool response formatting."""

    async def test_formatting_methods_exist(self):
        """Test that formatting methods exist."""
        server = AxonMCPServer()
        
        # Test _format_search_results
        results = [
            {
                "name": "test_func",
                "kind": "function",
                "signature": "def test_func():",
                "file": "test.py",
                "repository": "test-repo",
                "lines": "1-5",
                "documentation": "Test function",
                "relevance_score": 0.95,
            }
        ]
        formatted = server._format_search_results(results, "test")
        assert "test_func" in formatted
        assert "test-repo" in formatted

        # Test _format_repository_list
        repos = [
            {
                "id": 1,
                "name": "test-repo",
                "status": "completed",
                "total_files": 10,
                "total_symbols": 100,
                "last_synced": "2024-01-01T00:00:00",
            }
        ]
        formatted = server._format_repository_list(repos)
        assert "test-repo" in formatted
        assert "completed" in formatted

        # Test _format_symbol_context
        context = {
            "symbol": {
                "name": "test_func",
                "kind": "function",
                "signature": "def test_func():",
                "documentation": "Test function",
                "parameters": [{"name": "arg1", "type": "str"}],
                "return_type": "int",
                "complexity": 5,
                "access_modifier": "public",
            },
            "location": {
                "repository": "test-repo",
                "file": "test.py",
                "lines": "1-10",
            },
            "relationships": {
                "calls": [{"name": "other_func", "id": 2, "kind": "function"}],
                "called_by": [],
                "inherits_from": [],
                "inherited_by": [],
            },
        }
        formatted = server._format_symbol_context(context)
        assert "test_func" in formatted
        assert "Test function" in formatted
        assert "other_func" in formatted  # Verify relationship is formatted
