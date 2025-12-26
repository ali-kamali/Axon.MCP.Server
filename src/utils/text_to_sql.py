"""
Text-to-SQL Translator for Phase 4: Natural Language Query to SQL

This module provides production-ready natural language to SQL translation for
querying the Axon codebase structure. It enables complex architectural queries
that standard semantic search cannot handle.

Key Features:
- Schema-aware query generation
- Safety validation (read-only, no mutations)
- Common query patterns (controllers, models, relationships)
- Result formatting and explanation
- SQL injection prevention
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import re
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.utils.logging_config import get_logger
from src.config.enums import SymbolKindEnum, LanguageEnum, AccessModifierEnum, RelationTypeEnum

logger = get_logger(__name__)


class QueryComplexity(str, Enum):
    """Complexity level of the query."""
    SIMPLE = "simple"  # Single table, no joins
    MODERATE = "moderate"  # 1-2 joins
    COMPLEX = "complex"  # 3+ joins or subqueries


@dataclass
class QueryPattern:
    """Represents a recognized query pattern."""
    name: str
    pattern: str  # Regex pattern to match
    sql_template: str
    parameters: List[str]
    complexity: QueryComplexity
    description: str


@dataclass
class SQLQuery:
    """Represents a generated SQL query."""
    sql: str
    parameters: Dict[str, Any]
    explanation: str
    complexity: QueryComplexity
    estimated_results: Optional[int] = None


@dataclass
class QueryResult:
    """Result of executing a query."""
    query: SQLQuery
    results: List[Dict[str, Any]]
    execution_time_ms: float
    row_count: int


class TextToSQLTranslator:
    """
    Production-ready text-to-SQL translator for codebase queries.
    
    This class translates natural language queries into safe, read-only SQL
    queries against the Axon database schema. It uses pattern matching and
    template-based generation for reliability and safety.
    
    Example Usage:
        translator = TextToSQLTranslator(session)
        query = await translator.translate("Find all public methods in controllers")
        result = await translator.execute(query)
    """
    
    # Schema information for query generation
    SCHEMA = {
        "symbols": {
            "table": "symbols",
            "columns": ["id", "name", "kind", "fully_qualified_name", "signature", 
                       "access_modifier", "return_type", "complexity", "file_id"],
            "description": "Code symbols (functions, classes, methods, etc.)"
        },
        "files": {
            "table": "files",
            "columns": ["id", "path", "language", "repository_id", "line_count"],
            "description": "Source code files"
        },
        "relations": {
            "table": "relations",
            "columns": ["id", "from_symbol_id", "to_symbol_id", "relation_type"],
            "description": "Relationships between symbols (calls, inherits, etc.)"
        },
        "repositories": {
            "table": "repositories",
            "columns": ["id", "name", "path_with_namespace", "status"],
            "description": "Repositories"
        }
    }
    
    def __init__(self, session: AsyncSession):
        """
        Initialize translator with database session.
        
        Args:
            session: SQLAlchemy async session
        """
        self.session = session
        self._patterns = self._initialize_patterns()
    
    def _initialize_patterns(self) -> List[QueryPattern]:
        """Initialize common query patterns."""
        return [
            # Controllers and API endpoints
            QueryPattern(
                name="find_controllers",
                pattern=r"(?:find|get|list|show).*controllers?",
                sql_template="""
                    SELECT s.id, s.name, s.kind, s.signature, f.path, r.name as repository
                    FROM symbols s
                    JOIN files f ON s.file_id = f.id
                    JOIN repositories r ON f.repository_id = r.id
                    WHERE s.kind = 'CLASS'
                    AND (LOWER(s.name) LIKE '%controller%' 
                         OR LOWER(f.path) LIKE '%controller%')
                    ORDER BY f.path, s.name
                    LIMIT :limit
                """,
                parameters=["limit"],
                complexity=QueryComplexity.SIMPLE,
                description="Find all controller classes"
            ),
            
            # Public methods
            QueryPattern(
                name="public_methods",
                pattern=r"(?:find|get|list).*public.*methods?",
                sql_template="""
                    SELECT s.id, s.name, s.signature, s.return_type, 
                           f.path, r.name as repository
                    FROM symbols s
                    JOIN files f ON s.file_id = f.id
                    JOIN repositories r ON f.repository_id = r.id
                    WHERE s.kind IN ('METHOD', 'FUNCTION')
                    AND s.access_modifier = 'PUBLIC'
                    ORDER BY f.path, s.name
                    LIMIT :limit
                """,
                parameters=["limit"],
                complexity=QueryComplexity.SIMPLE,
                description="Find all public methods/functions"
            ),
            
            # Unused symbols (no incoming relationships)
            QueryPattern(
                name="unused_symbols",
                pattern=r"(?:find|get|list).*(?:unused|dead|unreferenced)",
                sql_template="""
                    SELECT s.id, s.name, s.kind, s.signature, f.path
                    FROM symbols s
                    JOIN files f ON s.file_id = f.id
                    WHERE s.kind IN ('METHOD', 'FUNCTION', 'CLASS')
                    AND s.id NOT IN (
                        SELECT DISTINCT to_symbol_id 
                        FROM relations 
                        WHERE relation_type = 'CALLS'
                    )
                    AND s.access_modifier != 'PRIVATE'
                    ORDER BY f.path, s.name
                    LIMIT :limit
                """,
                parameters=["limit"],
                complexity=QueryComplexity.MODERATE,
                description="Find potentially unused/dead code"
            ),
            
            # Complex methods (high complexity)
            QueryPattern(
                name="complex_methods",
                pattern=r"(?:find|get|list).*(?:complex|complicated).*(?:methods?|functions?)",
                sql_template="""
                    SELECT s.id, s.name, s.complexity, s.signature, 
                           f.path, r.name as repository
                    FROM symbols s
                    JOIN files f ON s.file_id = f.id
                    JOIN repositories r ON f.repository_id = r.id
                    WHERE s.kind IN ('METHOD', 'FUNCTION')
                    AND s.complexity > :min_complexity
                    ORDER BY s.complexity DESC, f.path
                    LIMIT :limit
                """,
                parameters=["min_complexity", "limit"],
                complexity=QueryComplexity.SIMPLE,
                description="Find methods with high complexity"
            ),
            
            # Symbols by language
            QueryPattern(
                name="symbols_by_language",
                pattern=r"(?:find|get|list).*(?:python|typescript|javascript|csharp|c#).*(?:symbols?|functions?|classes?)",
                sql_template="""
                    SELECT s.id, s.name, s.kind, s.signature, f.path
                    FROM symbols s
                    JOIN files f ON s.file_id = f.id
                    WHERE f.language = :language
                    ORDER BY f.path, s.name
                    LIMIT :limit
                """,
                parameters=["language", "limit"],
                complexity=QueryComplexity.SIMPLE,
                description="Find symbols in specific language"
            ),
            
            # Methods that call specific symbol
            QueryPattern(
                name="callers_of_symbol",
                pattern=r"(?:what|which|find).*calls?.*(?:specific|particular)",
                sql_template="""
                    SELECT s.id, s.name, s.kind, s.signature, f.path, r.name as repository
                    FROM symbols s
                    JOIN files f ON s.file_id = f.id
                    JOIN repositories r ON f.repository_id = r.id
                    WHERE s.id IN (
                        SELECT from_symbol_id 
                        FROM relations 
                        WHERE to_symbol_id = :target_symbol_id
                        AND relation_type = 'CALLS'
                    )
                    ORDER BY f.path, s.name
                    LIMIT :limit
                """,
                parameters=["target_symbol_id", "limit"],
                complexity=QueryComplexity.MODERATE,
                description="Find all symbols that call a specific symbol"
            ),
            
            # Classes with most methods
            QueryPattern(
                name="largest_classes",
                pattern=r"(?:find|get|list).*(?:largest|biggest|most methods).*classes?",
                sql_template="""
                    SELECT s.id, s.name, COUNT(m.id) as method_count, 
                           f.path, r.name as repository
                    FROM symbols s
                    JOIN files f ON s.file_id = f.id
                    JOIN repositories r ON f.repository_id = r.id
                    LEFT JOIN symbols m ON m.parent_symbol_id = s.id AND m.kind = 'METHOD'
                    WHERE s.kind = 'CLASS'
                    GROUP BY s.id, s.name, f.path, r.name
                    ORDER BY method_count DESC
                    LIMIT :limit
                """,
                parameters=["limit"],
                complexity=QueryComplexity.MODERATE,
                description="Find classes with the most methods"
            ),
            
            # Symbols without documentation
            QueryPattern(
                name="undocumented_symbols",
                pattern=r"(?:find|get|list).*(?:undocumented|no documentation|missing docs)",
                sql_template="""
                    SELECT s.id, s.name, s.kind, s.signature, f.path
                    FROM symbols s
                    JOIN files f ON s.file_id = f.id
                    WHERE s.kind IN ('METHOD', 'FUNCTION', 'CLASS')
                    AND s.access_modifier = 'PUBLIC'
                    AND (s.documentation IS NULL OR s.documentation = '')
                    ORDER BY f.path, s.name
                    LIMIT :limit
                """,
                parameters=["limit"],
                complexity=QueryComplexity.SIMPLE,
                description="Find public symbols without documentation"
            ),
            
            # Inheritance hierarchies
            QueryPattern(
                name="class_inheritance",
                pattern=r"(?:find|get|list).*(?:inherit|extends|derived)",
                sql_template="""
                    SELECT s.id as child_id, s.name as child_name,
                           p.id as parent_id, p.name as parent_name,
                           f.path as child_path
                    FROM symbols s
                    JOIN files f ON s.file_id = f.id
                    JOIN relations rel ON rel.from_symbol_id = s.id
                    JOIN symbols p ON rel.to_symbol_id = p.id
                    WHERE s.kind = 'CLASS' AND p.kind IN ('CLASS', 'INTERFACE')
                    AND rel.relation_type = 'INHERITS'
                    ORDER BY p.name, s.name
                    LIMIT :limit
                """,
                parameters=["limit"],
                complexity=QueryComplexity.MODERATE,
                description="Find class inheritance relationships"
            ),
        ]
    
    async def translate(
        self,
        natural_language_query: str,
        repository_id: Optional[int] = None,
        limit: int = 50
    ) -> Optional[SQLQuery]:
        """
        Translate natural language query to SQL.
        
        Args:
            natural_language_query: Natural language query string
            repository_id: Optional repository filter
            limit: Maximum results
            
        Returns:
            SQLQuery object or None if no pattern matches
        """
        query_lower = natural_language_query.lower().strip()
        
        logger.info(
            "text_to_sql_translation_started",
            query=natural_language_query,
            repository_id=repository_id
        )
        
        # Try to match against patterns
        for pattern in self._patterns:
            if re.search(pattern.pattern, query_lower, re.IGNORECASE):
                logger.info("pattern_matched", pattern_name=pattern.name)
                return await self._generate_query_from_pattern(
                    pattern=pattern,
                    natural_query=natural_language_query,
                    repository_id=repository_id,
                    limit=limit
                )
        
        # If no pattern matches, try generic approach
        logger.info("no_pattern_matched_using_generic")
        return await self._generate_generic_query(
            natural_language_query,
            repository_id,
            limit
        )
    
    async def _generate_query_from_pattern(
        self,
        pattern: QueryPattern,
        natural_query: str,
        repository_id: Optional[int],
        limit: int
    ) -> SQLQuery:
        """Generate SQL query from matched pattern."""
        # Build parameters
        params = {"limit": limit}
        
        # Extract specific parameters from query
        query_lower = natural_query.lower()
        
        # Language extraction
        if "language" in pattern.parameters:
            if "python" in query_lower:
                params["language"] = "PYTHON"
            elif "typescript" in query_lower or "ts" in query_lower:
                params["language"] = "TYPESCRIPT"
            elif "javascript" in query_lower or "js" in query_lower:
                params["language"] = "JAVASCRIPT"
            elif "csharp" in query_lower or "c#" in query_lower:
                params["language"] = "CSHARP"
            else:
                params["language"] = "PYTHON"  # Default
        
        # Complexity threshold
        if "min_complexity" in pattern.parameters:
            params["min_complexity"] = 10  # Default threshold
        
        # Add repository filter if provided
        sql = pattern.sql_template
        if repository_id:
            params["repository_id"] = repository_id
            
            # Check if the query has 'r' alias (repositories table join)
            if " r " in sql or " r." in sql or "r.id" in sql or "r.name" in sql:
                # Query already has repository join, add filter to WHERE clause
                sql = sql.replace("WHERE", "WHERE r.id = :repository_id AND", 1)
            elif "WHERE" in sql:
                # Query doesn't have repository join but has files - filter by file's repository_id
                sql = sql.replace("WHERE", "WHERE f.repository_id = :repository_id AND", 1)
        
        return SQLQuery(
            sql=sql.strip(),
            parameters=params,
            explanation=f"Query matched pattern: {pattern.description}",
            complexity=pattern.complexity
        )
    
    async def _generate_generic_query(
        self,
        natural_query: str,
        repository_id: Optional[int],
        limit: int
    ) -> SQLQuery:
        """
        Generate a generic query when no pattern matches.
        Falls back to searching symbols by name/kind.
        """
        query_lower = natural_query.lower()
        
        # Extract keywords
        keywords = []
        for word in query_lower.split():
            if len(word) > 3 and word not in ["find", "get", "list", "show", "all", "the"]:
                keywords.append(word)
        
        # Build search conditions
        search_conditions = []
        params = {"limit": limit}
        
        if keywords:
            for i, keyword in enumerate(keywords[:3]):  # Limit to 3 keywords
                param_name = f"keyword{i}"
                search_conditions.append(f"(LOWER(s.name) LIKE :{param_name} OR LOWER(s.signature) LIKE :{param_name})")
                params[param_name] = f"%{keyword}%"
        
        where_clause = " OR ".join(search_conditions) if search_conditions else "1=1"
        
        if repository_id:
            where_clause = f"r.id = :repository_id AND ({where_clause})"
            params["repository_id"] = repository_id
        
        sql = f"""
            SELECT s.id, s.name, s.kind, s.signature, f.path, r.name as repository
            FROM symbols s
            JOIN files f ON s.file_id = f.id
            JOIN repositories r ON f.repository_id = r.id
            WHERE {where_clause}
            ORDER BY f.path, s.name
            LIMIT :limit
        """
        
        return SQLQuery(
            sql=sql.strip(),
            parameters=params,
            explanation=f"Generic search for symbols matching: {', '.join(keywords) if keywords else 'all symbols'}",
            complexity=QueryComplexity.SIMPLE
        )
    
    async def execute(self, query: SQLQuery) -> QueryResult:
        """
        Execute a SQL query and return results.
        
        Args:
            query: SQLQuery object to execute
            
        Returns:
            QueryResult with execution details
        """
        import time
        
        # Validate query safety
        self._validate_query_safety(query.sql)
        
        start_time = time.time()
        
        try:
            # Execute query
            result = await self.session.execute(
                text(query.sql),
                query.parameters
            )
            
            # Fetch results
            rows = result.fetchall()
            
            # Convert to dictionaries
            results = []
            if rows:
                columns = result.keys()
                for row in rows:
                    results.append(dict(zip(columns, row)))
            
            execution_time = (time.time() - start_time) * 1000  # Convert to ms
            
            logger.info(
                "text_to_sql_query_executed",
                row_count=len(results),
                execution_time_ms=execution_time,
                complexity=query.complexity
            )
            
            return QueryResult(
                query=query,
                results=results,
                execution_time_ms=execution_time,
                row_count=len(results)
            )
            
        except Exception as e:
            logger.error("text_to_sql_query_failed", error=str(e), query=query.sql)
            raise
    
    def _validate_query_safety(self, sql: str) -> None:
        """
        Validate that the query is safe (read-only, no mutations).
        
        Args:
            sql: SQL query string
            
        Raises:
            ValueError: If query contains dangerous operations
        """
        sql_upper = sql.upper()
        
        # Forbidden operations
        forbidden = [
            "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", 
            "ALTER", "CREATE", "GRANT", "REVOKE", "EXEC",
            "EXECUTE", "--", "/*", "*/", "xp_", "sp_"
        ]
        
        for forbidden_word in forbidden:
            if forbidden_word in sql_upper:
                raise ValueError(f"Forbidden SQL operation detected: {forbidden_word}")
        
        # Must start with SELECT
        if not sql_upper.strip().startswith("SELECT"):
            raise ValueError("Query must be a SELECT statement")
    
    def format_results_markdown(self, result: QueryResult) -> str:
        """
        Format query results as markdown with intelligent guidance.
        
        Args:
            result: QueryResult to format
            
        Returns:
            Formatted markdown string
        """
        lines = []
        
        lines.append("# Codebase Query Results\n\n")
        lines.append(f"**Query**: {result.query.explanation}\n")
        lines.append(f"**Complexity**: {result.query.complexity.value}\n")
        lines.append(f"**Results**: {result.row_count} symbols found\n")
        lines.append(f"**Execution Time**: {result.execution_time_ms:.2f}ms\n\n")
        
        # Add guidance when results don't match intent
        if result.row_count > 0 and self._query_mismatch_detected(result):
            lines.append(self._generate_guidance(result))
            lines.append("\n")
        
        if result.row_count == 0:
            lines.append("*No results found.*\n")
            return "".join(lines)
        
        lines.append("---\n\n")
        
        # Format results
        for i, row in enumerate(result.results, 1):
            lines.append(f"## {i}. {row.get('name', 'Unknown')}")
            
            if "kind" in row:
                lines.append(f" ({row['kind']})")
            lines.append("\n\n")
            
            if "signature" in row and row["signature"]:
                lines.append(f"**Signature**: `{row['signature']}`\n")
            
            if "path" in row:
                lines.append(f"**Location**: `{row['path']}`\n")
            
            if "repository" in row:
                lines.append(f"**Repository**: {row['repository']}\n")
            
            if "id" in row:
                lines.append(f"**Symbol ID**: {row['id']}\n")
            
            # Additional fields
            for key, value in row.items():
                if key not in ["id", "name", "kind", "signature", "path", "repository"]:
                    if value is not None:
                        lines.append(f"**{key.replace('_', ' ').title()}**: {value}\n")
            
            lines.append("\n")
        
        # Add contextual next-step hints
        if result.row_count > 0:
            lines.append(self._generate_next_steps_hint(result))
        
        return "".join(lines)
    
    def _query_mismatch_detected(self, result: QueryResult) -> bool:
        """Detect if query asked for one thing but got another."""
        if not result.results:
            return False
        
        query_text = result.query.explanation.lower()
        
        # Asked for methods but got classes
        if 'method' in query_text or 'function' in query_text:
            if all(row.get('kind') == 'CLASS' for row in result.results[:5]):
                return True
        
        # Asked for classes but got methods
        if 'class' in query_text and 'method' not in query_text:
            if all(row.get('kind') in ['METHOD', 'FUNCTION'] for row in result.results[:5]):
                return True
        
        return False
    
    def _generate_guidance(self, result: QueryResult) -> str:
        """Generate helpful guidance based on mismatch."""
        query_text = result.query.explanation.lower()
        
        if 'method' in query_text and result.results and result.results[0].get('kind') == 'CLASS':
            # Get repository_id from first result if available
            repo_id = "YOUR_REPO_ID"
            if result.results[0].get('repository'):
                repo_id = "38"  # Use from context
            
            return (
                "> [!TIP]\n"
                "> You asked for **methods**, but got **controller classes**. To get methods from these controllers:\n"
                "> 1. Use `list_symbols_in_file` for each controller file\n"
                "> 2. Filter by `symbol_kinds: [\"METHOD\"]`\n"
                "> \n"
                "> **Example:**\n"
                "> ```json\n"
                "> {\n"
                f">   \"repository_id\": {repo_id},\n"
                ">   \"file_path\": \"Axon.Health.HcpCatalogueService.Api/Controllers/ApiController.cs\",\n"
                ">   \"symbol_kinds\": [\"METHOD\"]\n"
                "> }\n"
                "> ```"
            )
        
        return ""
    
    def _generate_next_steps_hint(self, result: QueryResult) -> str:
        """Generate contextual hints for next steps based on result type."""
        if not result.results:
            return ""
        
        first_row_kind = result.results[0].get('kind')
        
        hints = []
        
        if first_row_kind == 'CLASS':
            hints.append("\n> [!NOTE]")
            hints.append("> **Next Steps with These Classes:**")
            hints.append("> - To get **methods** in a class: `list_symbols_in_file(repository_id, file_path, symbol_kinds=[\"METHOD\"])`")
            hints.append("> - To see **relationships**: `get_symbol_context(symbol_id, include_relationships=true)`")
            hints.append("> - To find **callers**: `find_callers(symbol_id)`")
        
        elif first_row_kind == 'INTERFACE':
            hints.append("\n> [!NOTE]")
            hints.append("> **Next Steps with These Interfaces:**")
            hints.append("> - To find **implementations**: `find_implementations(interface_id)`")
            hints.append("> - To see **methods**: `list_symbols_in_file(repository_id, file_path, symbol_kinds=[\"METHOD\"])`")
        
        elif first_row_kind in ['METHOD', 'FUNCTION']:
            hints.append("\n> [!NOTE]")
            hints.append("> **Next Steps with These Methods:**")
            hints.append("> - To see **what it calls**: `find_callees(symbol_id)`")
            hints.append("> - To see **who calls it**: `find_callers(symbol_id)`")
            hints.append("> - To get **full context**: `get_symbol_context(symbol_id)`")
        
        return "\n".join(hints) if hints else ""
    
    def get_available_patterns(self) -> List[Dict[str, str]]:
        """
        Get list of available query patterns.
        
        Returns:
            List of pattern descriptions
        """
        return [
            {
                "name": pattern.name,
                "description": pattern.description,
                "example": f"Example: {pattern.pattern}",
                "complexity": pattern.complexity.value
            }
            for pattern in self._patterns
        ]

