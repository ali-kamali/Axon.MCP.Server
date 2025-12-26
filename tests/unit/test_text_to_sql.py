"""
Unit tests for Text-to-SQL Translator (Phase 4: Natural Language Query to SQL).

These tests verify the production-ready text-to-SQL translation implementation,
including pattern matching, query generation, safety validation, and result formatting.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from src.utils.text_to_sql import (
    TextToSQLTranslator,
    SQLQuery,
    QueryResult,
    QueryComplexity,
    QueryPattern,
)


class TestQueryComplexity:
    """Test QueryComplexity enum."""
    
    def test_complexity_values(self):
        """Test enum values."""
        assert QueryComplexity.SIMPLE.value == "simple"
        assert QueryComplexity.MODERATE.value == "moderate"
        assert QueryComplexity.COMPLEX.value == "complex"


class TestSQLQuery:
    """Test SQLQuery dataclass."""
    
    def test_sql_query_creation(self):
        """Test creating a SQL query."""
        query = SQLQuery(
            sql="SELECT * FROM symbols WHERE name = :name",
            parameters={"name": "TestClass"},
            explanation="Find symbol by name",
            complexity=QueryComplexity.SIMPLE
        )
        assert query.sql == "SELECT * FROM symbols WHERE name = :name"
        assert query.parameters["name"] == "TestClass"
        assert query.complexity == QueryComplexity.SIMPLE


class TestTextToSQLTranslator:
    """Test TextToSQLTranslator class."""
    
    @pytest.fixture
    def mock_session(self):
        """Create mock async session."""
        session = AsyncMock(spec=AsyncSession)
        return session
    
    @pytest.fixture
    def translator(self, mock_session):
        """Create translator instance."""
        return TextToSQLTranslator(mock_session)
    
    @pytest.mark.asyncio
    async def test_translate_find_controllers(self, translator):
        """Test translating 'find controllers' query."""
        query = await translator.translate("find all controllers", limit=50)
        
        assert query is not None
        assert "SELECT" in query.sql.upper()
        assert "FROM symbols" in query.sql
        assert "controller" in query.sql.lower()
        assert query.parameters["limit"] == 50
    
    @pytest.mark.asyncio
    async def test_translate_public_methods(self, translator):
        """Test translating 'public methods' query."""
        query = await translator.translate("list all public methods", limit=100)
        
        assert query is not None
        assert "METHOD" in query.sql or "FUNCTION" in query.sql
        assert "PUBLIC" in query.sql
        assert query.parameters["limit"] == 100
    
    @pytest.mark.asyncio
    async def test_translate_unused_symbols(self, translator):
        """Test translating 'unused symbols' query."""
        query = await translator.translate("find unused functions", limit=30)
        
        assert query is not None
        assert "NOT IN" in query.sql or "NOT EXISTS" in query.sql
        assert query.parameters["limit"] == 30
    
    @pytest.mark.asyncio
    async def test_translate_complex_methods(self, translator):
        """Test translating 'complex methods' query."""
        query = await translator.translate("find methods with high complexity", limit=20)
        
        assert query is not None
        assert "SELECT" in query.sql.upper()
        # May match specific pattern or fall through to generic (both are fine)
        assert query.parameters["limit"] == 20
    
    @pytest.mark.asyncio
    async def test_translate_with_repository_filter(self, translator):
        """Test translating query with repository filter (using parameterized query)."""
        query = await translator.translate(
            "find all controllers",
            repository_id=5,
            limit=50
        )
        
        assert query is not None
        # Must use parameterized query (not string interpolation) - security fix
        assert query.parameters.get("repository_id") == 5
        assert ":repository_id" in query.sql
        # Should NOT have direct string interpolation (SQL injection risk)
        assert "r.id = 5" not in query.sql
    
    @pytest.mark.asyncio
    async def test_translate_python_symbols(self, translator):
        """Test translating language-specific query."""
        query = await translator.translate("find python classes", limit=50)
        
        assert query is not None
        assert query.parameters.get("language") == "PYTHON" or "python" in query.sql.lower()
    
    @pytest.mark.asyncio
    async def test_translate_typescript_symbols(self, translator):
        """Test translating TypeScript query."""
        query = await translator.translate("list typescript functions", limit=50)
        
        assert query is not None
        assert query.parameters.get("language") == "TYPESCRIPT" or "typescript" in query.sql.lower()
    
    @pytest.mark.asyncio
    async def test_translate_generic_query(self, translator):
        """Test translating query with no pattern match (generic)."""
        query = await translator.translate("search for something unusual", limit=50)
        
        assert query is not None
        assert "SELECT" in query.sql.upper()
        assert "FROM symbols" in query.sql
        assert query.complexity == QueryComplexity.SIMPLE
    
    @pytest.mark.asyncio
    async def test_execute_query(self, translator, mock_session):
        """Test executing a SQL query."""
        query = SQLQuery(
            sql="SELECT id, name FROM symbols LIMIT :limit",
            parameters={"limit": 10},
            explanation="Test query",
            complexity=QueryComplexity.SIMPLE
        )
        
        # Mock query execution
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (1, "TestClass"),
            (2, "TestFunction"),
        ]
        mock_result.keys.return_value = ["id", "name"]
        mock_session.execute.return_value = mock_result
        
        result = await translator.execute(query)
        
        assert result.row_count == 2
        assert len(result.results) == 2
        assert result.results[0]["id"] == 1
        assert result.results[0]["name"] == "TestClass"
        assert result.execution_time_ms >= 0
    
    @pytest.mark.asyncio
    async def test_execute_query_no_results(self, translator, mock_session):
        """Test executing query that returns no results."""
        query = SQLQuery(
            sql="SELECT id FROM symbols WHERE 1=0",
            parameters={},
            explanation="Test query",
            complexity=QueryComplexity.SIMPLE
        )
        
        # Mock empty results
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_result.keys.return_value = []
        mock_session.execute.return_value = mock_result
        
        result = await translator.execute(query)
        
        assert result.row_count == 0
        assert len(result.results) == 0
    
    def test_validate_query_safety_select(self, translator):
        """Test that SELECT queries pass validation."""
        # Should not raise
        translator._validate_query_safety("SELECT * FROM symbols")
        translator._validate_query_safety("select id, name from files")
    
    def test_validate_query_safety_insert(self, translator):
        """Test that INSERT queries are rejected."""
        with pytest.raises(ValueError, match="Forbidden SQL operation"):
            translator._validate_query_safety("INSERT INTO symbols VALUES (1, 'test')")
    
    def test_validate_query_safety_update(self, translator):
        """Test that UPDATE queries are rejected."""
        with pytest.raises(ValueError, match="Forbidden SQL operation"):
            translator._validate_query_safety("UPDATE symbols SET name='test'")
    
    def test_validate_query_safety_delete(self, translator):
        """Test that DELETE queries are rejected."""
        with pytest.raises(ValueError, match="Forbidden SQL operation"):
            translator._validate_query_safety("DELETE FROM symbols")
    
    def test_validate_query_safety_drop(self, translator):
        """Test that DROP queries are rejected."""
        with pytest.raises(ValueError, match="Forbidden SQL operation"):
            translator._validate_query_safety("DROP TABLE symbols")
    
    def test_validate_query_safety_sql_injection(self, translator):
        """Test that SQL injection attempts are rejected."""
        with pytest.raises(ValueError):
            translator._validate_query_safety("SELECT * FROM symbols; DROP TABLE users--")
    
    def test_validate_query_safety_must_be_select(self, translator):
        """Test that non-SELECT queries are rejected."""
        with pytest.raises(ValueError, match="must be a SELECT"):
            translator._validate_query_safety("SHOW TABLES")
    
    def test_format_results_markdown(self, translator):
        """Test formatting results as markdown."""
        query = SQLQuery(
            sql="SELECT * FROM symbols",
            parameters={},
            explanation="Test query for controllers",
            complexity=QueryComplexity.SIMPLE
        )
        
        result = QueryResult(
            query=query,
            results=[
                {
                    "id": 1,
                    "name": "UserController",
                    "kind": "CLASS",
                    "signature": "class UserController",
                    "path": "src/controllers/user_controller.py",
                    "repository": "my-app"
                },
                {
                    "id": 2,
                    "name": "CreateUser",
                    "kind": "METHOD",
                    "signature": "def CreateUser(self, request: UserRequest) -> User",
                    "path": "src/controllers/user_controller.py",
                    "repository": "my-app"
                }
            ],
            execution_time_ms=45.5,
            row_count=2
        )
        
        markdown = translator.format_results_markdown(result)
        
        assert "# Codebase Query Results" in markdown
        assert "UserController" in markdown
        assert "CreateUser" in markdown
        assert "CLASS" in markdown
        assert "METHOD" in markdown
        assert "45.5ms" in markdown or "45.50ms" in markdown
        assert "2 symbols found" in markdown
    
    def test_format_results_markdown_empty(self, translator):
        """Test formatting empty results."""
        query = SQLQuery(
            sql="SELECT * FROM symbols WHERE 1=0",
            parameters={},
            explanation="Empty query",
            complexity=QueryComplexity.SIMPLE
        )
        
        result = QueryResult(
            query=query,
            results=[],
            execution_time_ms=10.0,
            row_count=0
        )
        
        markdown = translator.format_results_markdown(result)
        
        assert "No results found" in markdown
        assert "0 symbols found" in markdown
    
    def test_get_available_patterns(self, translator):
        """Test getting list of available patterns."""
        patterns = translator.get_available_patterns()
        
        assert len(patterns) > 0
        assert all("name" in p for p in patterns)
        assert all("description" in p for p in patterns)
        assert all("complexity" in p for p in patterns)
        
        # Check for known patterns
        pattern_names = [p["name"] for p in patterns]
        assert "find_controllers" in pattern_names
        assert "public_methods" in pattern_names
    
    @pytest.mark.asyncio
    async def test_pattern_initialization(self, translator):
        """Test that patterns are initialized correctly."""
        patterns = translator._patterns
        
        assert len(patterns) > 0
        assert all(isinstance(p, QueryPattern) for p in patterns)
        assert all(hasattr(p, "name") for p in patterns)
        assert all(hasattr(p, "pattern") for p in patterns)
        assert all(hasattr(p, "sql_template") for p in patterns)
    
    @pytest.mark.asyncio
    async def test_translate_largest_classes(self, translator):
        """Test translating 'largest classes' query."""
        query = await translator.translate("find largest classes", limit=10)
        
        assert query is not None
        assert "COUNT" in query.sql or "count" in query.sql.lower()
        assert "CLASS" in query.sql
        assert query.complexity in [QueryComplexity.MODERATE, QueryComplexity.COMPLEX]
    
    @pytest.mark.asyncio
    async def test_translate_undocumented_symbols(self, translator):
        """Test translating 'undocumented' query."""
        query = await translator.translate("find undocumented methods", limit=50)
        
        assert query is not None
        assert "documentation" in query.sql.lower()
        assert "NULL" in query.sql or "IS NULL" in query.sql or "= ''" in query.sql
    
    @pytest.mark.asyncio
    async def test_translate_inheritance(self, translator):
        """Test translating inheritance query."""
        query = await translator.translate("find classes that inherit from BaseClass", limit=50)
        
        assert query is not None
        assert "SELECT" in query.sql.upper()
        # May match specific pattern or fall through to generic (both are fine)
        assert query.parameters["limit"] == 50
    
    @pytest.mark.asyncio
    async def test_execute_with_exception(self, translator, mock_session):
        """Test execute handling exceptions."""
        query = SQLQuery(
            sql="SELECT * FROM symbols",
            parameters={},
            explanation="Test",
            complexity=QueryComplexity.SIMPLE
        )
        
        mock_session.execute.side_effect = Exception("Database error")
        
        with pytest.raises(Exception, match="Database error"):
            await translator.execute(query)
    
    @pytest.mark.asyncio
    async def test_translate_case_insensitive(self, translator):
        """Test that translation is case-insensitive."""
        query1 = await translator.translate("FIND ALL CONTROLLERS")
        query2 = await translator.translate("find all controllers")
        query3 = await translator.translate("FiNd AlL cOnTrOlLeRs")
        
        assert query1 is not None
        assert query2 is not None
        assert query3 is not None
        # All should generate similar queries
        assert "controller" in query1.sql.lower()
        assert "controller" in query2.sql.lower()
        assert "controller" in query3.sql.lower()


class TestQueryPattern:
    """Test QueryPattern dataclass."""
    
    def test_query_pattern_creation(self):
        """Test creating a query pattern."""
        pattern = QueryPattern(
            name="test_pattern",
            pattern=r"test.*query",
            sql_template="SELECT * FROM symbols WHERE name LIKE :name",
            parameters=["name"],
            complexity=QueryComplexity.SIMPLE,
            description="Test pattern"
        )
        
        assert pattern.name == "test_pattern"
        assert pattern.complexity == QueryComplexity.SIMPLE
        assert "name" in pattern.parameters


class TestQueryResult:
    """Test QueryResult dataclass."""
    
    def test_query_result_creation(self):
        """Test creating a query result."""
        query = SQLQuery(
            sql="SELECT * FROM symbols",
            parameters={},
            explanation="Test",
            complexity=QueryComplexity.SIMPLE
        )
        
        result = QueryResult(
            query=query,
            results=[{"id": 1, "name": "Test"}],
            execution_time_ms=50.0,
            row_count=1
        )
        
        assert result.row_count == 1
        assert result.execution_time_ms == 50.0
        assert len(result.results) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

