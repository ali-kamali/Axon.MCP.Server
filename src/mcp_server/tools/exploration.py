import time
from typing import List, Optional

from mcp.types import TextContent

from src.config.enums import MCPToolEnum
from src.database.session import get_async_session
from src.utils.logging_config import get_logger
from src.utils.metrics import mcp_tool_calls_total, mcp_tool_duration
from src.utils.project_mapper import ProjectMapper
from src.utils.module_summary_generator import ModuleSummaryGenerator
from src.utils.text_to_sql import TextToSQLTranslator
from src.mcp_server.formatters.hierarchy import format_module_summary

logger = get_logger(__name__)

async def get_project_map(
    repository_id: int,
    max_depth: int = 2,
) -> List[TextContent]:
    """
    Get high-level project map showing modules and their relationships.

    Args:
        repository_id: Repository ID
        max_depth: Maximum depth for module mapping

    Returns:
        Project map
    """
    # Validate required parameters
    if repository_id is None:
        return [
            TextContent(
                type="text",
                text="❌ Missing required parameter: repository_id\n\n"
                "💡 Use `list_repositories()` to find available repositories and their IDs."
            )
        ]
    
    start_time = time.time()

    try:
        async with get_async_session() as session:
            mapper = ProjectMapper(session)
            project_map = await mapper.generate_project_map(
                repository_id=repository_id, max_depth=max_depth
            )

            duration = time.time() - start_time
            mcp_tool_duration.labels(tool_name=MCPToolEnum.GET_PROJECT_MAP.value).observe(
                duration
            )
            mcp_tool_calls_total.labels(
                tool_name=MCPToolEnum.GET_PROJECT_MAP.value, status="success"
            ).inc()

            logger.info(
                "mcp_get_project_map_success",
                repository_id=repository_id,
                max_depth=max_depth,
                duration=duration,
            )

            return [TextContent(type="text", text=project_map)]

    except Exception as e:
        duration = time.time() - start_time
        mcp_tool_calls_total.labels(
            tool_name=MCPToolEnum.GET_PROJECT_MAP.value, status="error"
        ).inc()
        logger.error(
            "mcp_get_project_map_failed",
            repository_id=repository_id,
            max_depth=max_depth,
            error=str(e),
            error_type=type(e).__name__,
            duration=duration,
            exc_info=True,
        )
        return [
            TextContent(
                type="text",
                text=f"\u274c Failed to generate project map: {str(e)}\n\n"
                f"Error type: {type(e).__name__}\n\n"
                f"\ud83d\udca1 Tips:\n"
                f"- Verify the repository ID is correct using `list_repositories()`\n"
                f"- Check that the repository has been successfully synced\n"
                f"- Try with a smaller max_depth value (e.g., 1 or 2)",
            )
        ]


async def get_module_summary(
    repository_id: int,
    module_path: str,
    generate_if_missing: bool = True
) -> List[TextContent]:
    """
    Get AI-generated summary for a specific module.

    Args:
        repository_id: Repository ID
        module_path: Path to module (e.g., "src/api", "backend/auth")
        generate_if_missing: Generate summary if it doesn't exist (default: True)

    Returns:
        Module summary with purpose, key components, and entry points
    """
    # Validate required parameters
    if repository_id is None:
        return [
            TextContent(
                type="text",
                text="❌ Missing required parameter: repository_id\n\n"
                "💡 Use `list_repositories()` to find available repositories and their IDs."
            )
        ]
    
    if not module_path:
        return [
            TextContent(
                type="text",
                text="❌ Missing required parameter: module_path\n\n"
                "💡 Use `get_project_map(repository_id)` to see available module paths.\n"
                "Example: 'src/api', 'backend/auth', 'frontend/components'"
            )
        ]
    
    start_time = time.time()

    try:
        async with get_async_session() as session:
            generator = ModuleSummaryGenerator(session)
            summary = await generator.get_module_summary(
                repository_id=repository_id,
                module_path=module_path,
                generate_if_missing=generate_if_missing
            )

            if not summary:
                return [
                    TextContent(
                        type="text",
                        text=f"❌ Module summary not found for '{module_path}' in repository {repository_id}.\n\n"
                        f"The module may not exist or may not have been analyzed yet.\n\n"
                        f"💡 Tips:\n"
                        f"- Use `get_project_map(repository_id={repository_id})` to see available modules\n"
                        f"- Ensure the repository has been fully indexed\n"
                        f"- Check that the module path is correct (e.g., 'src/api', not 'src/api/')",
                    )
                ]

            # Format summary for display
            formatted = format_module_summary(summary)

            duration = time.time() - start_time
            mcp_tool_duration.labels(tool_name=MCPToolEnum.GET_MODULE_SUMMARY.value).observe(
                duration
            )
            mcp_tool_calls_total.labels(
                tool_name=MCPToolEnum.GET_MODULE_SUMMARY.value, status="success"
            ).inc()

            logger.info(
                "mcp_get_module_summary_success",
                repository_id=repository_id,
                module_path=module_path,
                duration=duration,
            )

            return [TextContent(type="text", text=formatted)]

    except Exception as e:
        duration = time.time() - start_time
        mcp_tool_calls_total.labels(
            tool_name=MCPToolEnum.GET_MODULE_SUMMARY.value, status="error"
        ).inc()
        logger.error(
            "mcp_get_module_summary_failed",
            repository_id=repository_id,
            module_path=module_path,
            error=str(e),
            exc_info=True,
        )
        return [
            TextContent(
                type="text",
                text=f"Failed to get module summary: {str(e)}",
            )
        ]


async def query_codebase_structure(
    query: str,
    repository_id: Optional[int] = None,
    limit: int = 50
) -> List[TextContent]:
    """
    Query codebase structure using natural language (Phase 4: Text-to-SQL).
    
    Translates natural language queries into SQL queries against the codebase schema,
    enabling complex architectural queries that semantic search cannot handle.
    
    Args:
        query: Natural language query (e.g., "Find all public methods in controllers")
        repository_id: Optional repository filter
        limit: Maximum results (default: 50)
        
    Returns:
        Query results with symbols matching the criteria
    """
    # Validate required parameters
    if not query:
        return [
            TextContent(
                type="text",
                text="❌ Missing required parameter: query\n\n"
                "💡 Examples of valid queries:\n"
                "- Find all controllers\n"
                "- List public methods\n"
                "- Show complex methods\n"
                "- Find undocumented symbols\n"
                "- Get Python/TypeScript/CSharp classes\n"
                "- Find unused symbols\n"
                "- Show largest classes"
            )
        ]
    
    start_time = time.time()
    
    try:
        async with get_async_session() as session:
            translator = TextToSQLTranslator(session)
            
            # Translate natural language to SQL
            sql_query = await translator.translate(
                natural_language_query=query,
                repository_id=repository_id,
                limit=limit
            )
            
            if not sql_query:
                return [
                    TextContent(
                        type="text",
                        text=f"❌ Could not translate query: '{query}'\n\n"
                        f"💡 Try one of these supported patterns:\n"
                        f"- Find all controllers\n"
                        f"- List public methods\n"
                        f"- Show complex methods\n"
                        f"- Find undocumented symbols\n"
                        f"- Get Python/TypeScript/CSharp classes\n"
                        f"- Find unused symbols\n"
                        f"- Show largest classes\n"
                        f"- List inheritance hierarchies"
                    )
                ]
            
            # Execute query
            result = await translator.execute(sql_query)
            
            # Format results
            formatted_text = translator.format_results_markdown(result)
            
            duration = time.time() - start_time
            mcp_tool_duration.labels(tool_name="query_codebase_structure").observe(duration)
            mcp_tool_calls_total.labels(tool_name="query_codebase_structure", status="success").inc()
            
            logger.info(
                "mcp_query_codebase_structure_complete",
                query=query,
                row_count=result.row_count,
                execution_time_ms=result.execution_time_ms,
                duration=duration
            )
            
            return [TextContent(type="text", text=formatted_text)]
            
    except ValueError as e:
        # Safety validation error
        logger.warning("mcp_query_codebase_structure_validation_failed", error=str(e), query=query)
        mcp_tool_calls_total.labels(tool_name="query_codebase_structure", status="error").inc()
        return [
            TextContent(
                type="text",
                text=f"❌ Query validation failed: {str(e)}\n\n"
                f"Queries must be safe, read-only operations."
            )
        ]
    except Exception as e:
        logger.error(
            "mcp_query_codebase_structure_failed",
            query=query,
            error=str(e),
            exc_info=True
        )
        mcp_tool_calls_total.labels(tool_name="query_codebase_structure", status="error").inc()
        return [
            TextContent(
                type="text",
                text=f"Failed to query codebase structure: {str(e)}",
            )
        ]
