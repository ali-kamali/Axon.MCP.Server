import time
import re
from typing import List, Optional, Dict
from sqlalchemy import select, and_, or_, func

from mcp.types import TextContent

from src.api.services.search_service import SearchService
from src.config.enums import LanguageEnum, SymbolKindEnum
from src.database.models import File, Repository, Symbol
from src.database.session import get_async_session
from src.utils.logging_config import get_logger
from src.utils.metrics import mcp_tool_calls_total, mcp_tool_duration
from src.mcp_server.formatters.search import format_search_results

logger = get_logger(__name__)

async def search_code(
    query: str,
    limit: int = 10,
    repository_name: Optional[str] = None,
    language: Optional[str] = None,
    symbol_kind: Optional[str] = None,
) -> List[TextContent]:
    """
    Search for code symbols across repositories.

    Args:
        query: Search query (function name, class name, or description)
        limit: Maximum number of results (default: 10, max: 50)
        repository_name: Filter by repository name
        language: Filter by programming language (csharp, javascript, typescript, vue)
        symbol_kind: Filter by symbol kind (function, class, method, etc.)

    Returns:
        List of matching code symbols with their locations and documentation
    """
    start_time = time.time()

    try:
        mcp_tool_calls_total.labels(tool_name="search_code", status="started").inc()

        async with get_async_session() as session:
            search_service = SearchService(session)

            # Convert string enums
            language_enum = LanguageEnum(language) if language else None
            symbol_kind_enum = SymbolKindEnum(symbol_kind) if symbol_kind else None

            # Get repository ID if name provided
            repository_id = None
            if repository_name:
                result = await session.execute(
                    select(Repository).where(Repository.name == repository_name)
                )
                # Use first() instead of scalar_one_or_none() to handle duplicate repo names
                repo = result.scalars().first()
                if repo:
                    repository_id = repo.id

            results = await search_service.search(
                query=query,
                limit=min(limit, 50),
                repository_id=repository_id,
                language=language_enum,
                symbol_kind=symbol_kind_enum,
                hybrid=True,
            )

            # Format results for ChatGPT with IDs for cross-referencing
            formatted_results = []
            for result in results:
                formatted_results.append(
                    {
                        # IDs for drilling down (ENHANCED)
                        "symbol_id": result.symbol_id,
                        "file_id": result.file_id,
                        "repository_id": result.repository_id,
                        # Symbol info
                        "name": result.name,
                        "kind": result.kind.value,
                        "signature": result.signature,
                        "fully_qualified_name": result.fully_qualified_name,
                        # Location
                        "file": result.file_path,
                        "repository": result.repository_name,
                        "lines": f"{result.start_line}-{result.end_line}",
                        # Code content (ENHANCED)
                        "code_snippet": result.code_snippet,
                        "documentation": result.documentation
                        or "No documentation available",
                         # Search metadata
                        "relevance_score": round(result.score, 3),
                        "match_type": result.match_type,
                        # Quick access (ENHANCED)
                        "context_url": result.context_url,
                    }
                )

            duration = time.time() - start_time
            mcp_tool_duration.labels(tool_name="search_code").observe(duration)
            mcp_tool_calls_total.labels(
                tool_name="search_code", status="success"
            ).inc()

            return [
                TextContent(
                    type="text",
                    text=format_search_results(formatted_results, query),
                )
            ]

    except Exception as e:
        logger.error("mcp_search_failed", error=str(e), exc_info=True)
        mcp_tool_calls_total.labels(tool_name="search_code", status="error").inc()

        return [TextContent(type="text", text=f"Search failed: {str(e)}")]


async def search_documentation(
    query: str,
    repository_id: Optional[int] = None,
    doc_type: Optional[str] = None,
    limit: int = 10,
) -> List[TextContent]:
    """
    Search markdown documentation files.

    Args:
        query: Search query
        repository_id: Optional repository ID filter
        doc_type: Optional document type filter
        limit: Maximum results

    Returns:
        List of matching documentation sections
    """
    try:
        async with get_async_session() as session:
            # Search in Symbol table for DOCUMENT_SECTION and CODE_EXAMPLE kinds
            
            filters = [
                Symbol.kind.in_([SymbolKindEnum.DOCUMENT_SECTION, SymbolKindEnum.CODE_EXAMPLE])
            ]
            
            # Add text search filters
            search_filters = [
                Symbol.name.ilike(f"%{query}%"),
                Symbol.documentation.ilike(f"%{query}%"),
                Symbol.signature.ilike(f"%{query}%"),
            ]
            filters.append(or_(*search_filters))
            
            # Add repository filter
            if repository_id:
                filters.append(File.repository_id == repository_id)
            
            query_stmt = (
                select(Symbol, File, Repository)
                .join(File, Symbol.file_id == File.id)
                .join(Repository, File.repository_id == Repository.id)
                .where(and_(*filters))
                .limit(limit)
            )
            
            result = await session.execute(query_stmt)
            rows = result.all()
            
            if not rows:
                return [
                    TextContent(
                        type="text",
                        text=f"No documentation found for query: '{query}'",
                    )
                ]
            
            # Format results
            formatted = [f"Found {len(rows)} documentation sections for '{query}':\n\n"]
            
            for symbol, file, repo in rows:
                formatted.append(
                    f"## {symbol.name}\n"
                    f"**Repository**: {repo.name}\n"
                    f"**File**: {file.path} (line {symbol.start_line})\n"
                    f"**Type**: {symbol.kind.value}\n\n"
                )
                
                if symbol.documentation:
                    doc_preview = symbol.documentation[:300]
                    if len(symbol.documentation) > 300:
                        doc_preview += "..."
                    formatted.append(f"{doc_preview}\n\n")
                
                formatted.append("---\n\n")
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_search_documentation_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to search documentation: {str(e)}",
            )
        ]


async def search_configuration(
    key_pattern: str,
    repository_id: Optional[int] = None,
    environment: Optional[str] = None,
    limit: int = 20,
) -> List[TextContent]:
    """
    Search configuration settings.

    Args:
        key_pattern: Configuration key pattern (supports wildcards like 'Database:*')
        repository_id: Optional repository ID filter
        environment: Optional environment filter
        limit: Maximum results

    Returns:
        List of matching configuration entries
    """
    try:
        async with get_async_session() as session:
            from src.database.models import ConfigurationEntry
            
            filters = []
            
            # Convert wildcard pattern to SQL LIKE pattern
            like_pattern = key_pattern.replace('*', '%')
            filters.append(ConfigurationEntry.config_key.ilike(like_pattern))
            
            # Add repository filter
            if repository_id:
                filters.append(ConfigurationEntry.repository_id == repository_id)
            
            # Add environment filter
            if environment:
                filters.append(ConfigurationEntry.environment == environment)
            
            query_stmt = (
                select(ConfigurationEntry, Repository)
                .join(Repository, ConfigurationEntry.repository_id == Repository.id)
                .where(and_(*filters))
                .limit(limit)
            )
            
            result = await session.execute(query_stmt)
            rows = result.all()
            
            if not rows:
                return [
                    TextContent(
                        type="text",
                        text=f"No configuration found for pattern: '{key_pattern}'",
                    )
                ]
            
            # Format results
            formatted = [f"Found {len(rows)} configuration settings matching '{key_pattern}':\n\n"]
            
            for config, repo in rows:
                is_secret = config.is_secret == 1
                value = config.config_value if not is_secret else '[REDACTED]'
                
                formatted.append(
                    f"**{config.config_key}** {'🔒' if is_secret else ''}\n"
                    f"Repository: {repo.name}\n"
                    f"File: {config.file_path}\n"
                    f"Environment: {config.environment}\n"
                    f"Type: {config.config_type}\n"
                    f"Value: `{value}`\n\n"
                    "---\n\n"
                )
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_search_configuration_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to search configuration: {str(e)}",
            )
        ]


async def search_by_path(
    repository_id: int,
    path_pattern: str,
    limit: int = 50,
) -> List[TextContent]:
    """
    Search for files by path pattern.

    Args:
        repository_id: Repository ID
        path_pattern: Path pattern with wildcards (e.g., '*/services/*.cs')
        limit: Maximum results

    Returns:
        List of matching files
    """
    try:
        async with get_async_session() as session:
            
            # Get repository
            result = await session.execute(
                select(Repository).where(Repository.id == repository_id)
            )
            repo = result.scalar_one_or_none()
            
            if not repo:
                return [TextContent(type="text", text=f"Repository ID {repository_id} not found")]
            
            # Get all files in repository
            result = await session.execute(
                select(File).where(File.repository_id == repository_id)
            )
            files = result.scalars().all()
            
            # Convert glob pattern to regex
            regex_pattern = path_pattern.replace('**', '<DOUBLE_STAR>')
            regex_pattern = regex_pattern.replace('*', '[^/]*')
            regex_pattern = regex_pattern.replace('<DOUBLE_STAR>', '.*')
            regex_pattern = f"^{regex_pattern}$"
            
            # Filter files by pattern
            matching_files = []
            for file in files:
                if re.match(regex_pattern, file.path, re.IGNORECASE):
                    matching_files.append(file)
                    if len(matching_files) >= limit:
                        break
            
            if not matching_files:
                return [TextContent(type="text", text=f"No files match pattern: '{path_pattern}'")]
            
            # Get symbol counts for matching files
            file_ids = [file.id for file in matching_files]
            symbol_counts_result = await session.execute(
                select(
                    Symbol.file_id,
                    func.count(Symbol.id).label('count')
                )
                .where(Symbol.file_id.in_(file_ids))
                .group_by(Symbol.file_id)
            )
            symbol_counts = {row.file_id: row.count for row in symbol_counts_result}
            
            # Format results
            formatted = [
                f"# Files matching '{path_pattern}'\n",
                f"Repository: **{repo.name}**\n",
                f"Found: {len(matching_files)} files\n\n"
            ]
            
            for file in matching_files:
                symbol_count = symbol_counts.get(file.id, 0)
                formatted.append(
                    f"## {file.path}\n"
                    f"- **Language**: {file.language.value}\n"
                    f"- **Lines**: {file.line_count}\n"
                    f"- **Symbols**: {symbol_count}\n"
                    f"- **Size**: {file.size_bytes} bytes\n\n"
                )
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_search_by_path_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to search by path: {str(e)}",
            )
        ]
