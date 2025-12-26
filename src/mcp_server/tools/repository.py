from typing import List, Optional
from sqlalchemy import select, func, and_

from mcp.types import TextContent

from src.config.enums import SourceControlProviderEnum, SymbolKindEnum
from src.database.models import File, Repository, Symbol
from src.database.session import get_async_session
from src.utils.logging_config import get_logger
from src.mcp_server.formatters.repository import format_repository_list

logger = get_logger(__name__)

async def list_repositories(limit: int = 20) -> List[TextContent]:
    """
    List available repositories.

    Args:
        limit: Maximum number of repositories to return

    Returns:
        List of repositories with their status and statistics
    """
    try:
        async with get_async_session() as session:
            result = await session.execute(select(Repository).limit(limit))
            repos = result.scalars().all()

            repo_list = []
            for repo in repos:
                repo_list.append(
                    {
                        # Primary ID (ENHANCED)
                        "id": repo.id,
                        # Basic info
                        "name": repo.name,
                        "provider": repo.provider.value,
                        "path_with_namespace": repo.path_with_namespace,
                        # Access URLs (ENHANCED)
                        "url": repo.url,
                        "clone_url": repo.clone_url,
                        "default_branch": repo.default_branch,
                        # Status and stats
                        "status": repo.status.value,
                        "total_files": repo.total_files,
                        "total_symbols": repo.total_symbols,
                        "size_bytes": repo.size_bytes,
                        # Timestamps
                        "last_synced": repo.last_synced_at.isoformat()
                        if repo.last_synced_at
                        else None,
                        "last_commit_sha": repo.last_commit_sha,
                        "created_at": repo.created_at.isoformat() if repo.created_at else None,
                        # Provider-specific (ENHANCED)
                        "gitlab_project_id": repo.gitlab_project_id,
                        "azuredevops_project_name": repo.azuredevops_project_name,
                        "azuredevops_repo_id": repo.azuredevops_repo_id,
                    }
                )

            return [
                TextContent(
                    type="text",
                    text=format_repository_list(repo_list),
                )
            ]

    except Exception as e:
        logger.error("mcp_list_repositories_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to list repositories: {str(e)}",
            )
        ]


async def get_file_tree(
    repository_id: int,
    path: str = "",
    depth: int = 3,
) -> List[TextContent]:
    """
    Get directory tree structure.

    Args:
        repository_id: Repository ID
        path: Optional path to start from
        depth: Maximum depth to traverse

    Returns:
        Directory tree
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
                select(File).where(File.repository_id == repository_id).order_by(File.path)
            )
            files = result.scalars().all()
            
            # Get symbol counts per file (since File model doesn't have symbol_count attribute)
            file_ids = [f.id for f in files]
            symbol_counts_result = await session.execute(
                select(
                    Symbol.file_id,
                    func.count(Symbol.id).label('count')
                )
                .where(Symbol.file_id.in_(file_ids))
                .group_by(Symbol.file_id)
            ) if file_ids else None
            symbol_counts = {row.file_id: row.count for row in symbol_counts_result} if symbol_counts_result else {}
            
            # Build tree structure
            tree = {}
            start_path = path.rstrip('/')
            file_to_symbol_count = {}  # Map file path to symbol count
            
            for file in files:
                # Filter by starting path
                if start_path and not file.path.startswith(start_path):
                    continue
                
                parts = file.path.split('/')
                current = tree
                
                for part in parts[:-1]:  # directories
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                
                # Add file with its symbol count
                file_to_symbol_count[file.path] = symbol_counts.get(file.id, 0)
                current[parts[-1]] = file
            
            # Format tree
            def format_tree(node, indent=0, max_depth=depth):
                if indent >= max_depth:
                    return []
                
                lines = []
                items = sorted(node.items())
                
                for name, value in items:
                    prefix = "  " * indent
                    if isinstance(value, dict):
                        # Directory
                        file_count = sum(1 for v in value.values() if isinstance(v, File))
                        lines.append(f"{prefix}📁 **{name}/** ({file_count} files)\n")
                        lines.extend(format_tree(value, indent + 1, max_depth))
                    else:
                        # File
                        file_obj = value
                        sym_count = file_to_symbol_count.get(file_obj.path, 0)
                        lines.append(
                            f"{prefix}📄 {name} ({file_obj.language.value}, {sym_count} symbols)\n"
                        )
                
                return lines
            
            formatted = [
                f"# File Tree: {repo.name}\n",
                f"Path: {'/' if not start_path else start_path}\n",
                f"Total Files: {len(files)}\n\n"
            ]
            formatted.extend(format_tree(tree))
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_get_file_tree_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to get file tree: {str(e)}",
            )
        ]


async def get_file_content(
    repository_id: int,
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> List[TextContent]:
    """
    Read file content with line numbers.

    Args:
        repository_id: Repository ID
        file_path: Path to file within repository
        start_line: Optional start line (1-indexed)
        end_line: Optional end line (1-indexed)

    Returns:
        File content with line numbers and symbols
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
            
            # Get file record
            result = await session.execute(
                select(File).where(
                    File.repository_id == repository_id,
                    File.path == file_path
                )
            )
            file_record = result.scalar_one_or_none()
            
            if not file_record:
                return [TextContent(type="text", text=f"File '{file_path}' not found in repository")]
            
            # Try to read file content from disk
            # Construct file path from repository cache
            from src.gitlab.repository_manager import RepositoryManager
            from src.azuredevops.repository_manager import AzureDevOpsRepositoryManager
            
            # Select appropriate repository manager based on provider
            if repo.provider == SourceControlProviderEnum.GITLAB:
                repo_manager = RepositoryManager()
                repo_path = repo_manager.cache_dir / repo.path_with_namespace.replace("/", "_")
            elif repo.provider == SourceControlProviderEnum.AZUREDEVOPS:
                repo_manager = AzureDevOpsRepositoryManager()
                if not repo.azuredevops_project_name:
                    return [TextContent(type="text", text=f"Azure DevOps project name not set for repository {repository_id}")]
                repo_path = repo_manager.get_repository_path(repo.azuredevops_project_name, repo.name)
            else:
                return [TextContent(type="text", text=f"Unsupported provider: {repo.provider}")]
            
            full_file_path = repo_path / file_path
            
            if not full_file_path.exists():
                return [TextContent(type="text", text=f"File not found on disk: {file_path}")]
            
            # Read file content
            with open(full_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            # Apply line range if specified
            if start_line is not None:
                start_idx = max(0, start_line - 1)
            else:
                start_idx = 0
            
            if end_line is not None:
                end_idx = min(len(lines), end_line)
            else:
                end_idx = len(lines)
            
            # Format with line numbers
            numbered_lines = []
            for i, line in enumerate(lines[start_idx:end_idx], start=start_idx + 1):
                numbered_lines.append(f"{i:6d}| {line.rstrip()}")
            
            content = '\n'.join(numbered_lines)
            
            # Get symbols in this file
            result = await session.execute(
                select(Symbol).where(Symbol.file_id == file_record.id).order_by(Symbol.start_line)
            )
            symbols = result.scalars().all()
            
            # Format response
            formatted = [
                f"# {file_path}\n",
                f"Repository: **{repo.name}**\n",
                f"Language: {file_record.language.value}\n",
                f"Total Lines: {len(lines)}\n",
                f"Symbols: {len(symbols)}\n\n",
                "## Content:\n\n",
                f"```{file_record.language.value}\n",
                content,
                "\n```\n\n",
                "## Symbols in this file:\n\n"
            ]
            
            for symbol in symbols:
                formatted.append(
                    f"- **{symbol.name}** ({symbol.kind.value}) - Line {symbol.start_line}\n"
                )
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_get_file_content_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to get file content: {str(e)}",
            )
        ]


async def list_symbols_in_file(
    repository_id: int,
    file_path: str,
    symbol_kinds: Optional[List[str]] = None,
) -> List[TextContent]:
    """
    List all symbols in a specific file.

    Args:
        repository_id: Repository ID
        file_path: Path to file
        symbol_kinds: Optional filter by kinds

    Returns:
        List of symbols
    """
    try:
        async with get_async_session() as session:
            
            # Get file record
            result = await session.execute(
                select(File).where(
                    File.repository_id == repository_id,
                    File.path == file_path
                )
            )
            file_record = result.scalar_one_or_none()
            
            if not file_record:
                return [TextContent(type="text", text=f"File '{file_path}' not found in repository")]
            
            # Build filters
            filters = [Symbol.file_id == file_record.id]
            
            if symbol_kinds:
                try:
                    kinds = [SymbolKindEnum(k) for k in symbol_kinds]
                    filters.append(Symbol.kind.in_(kinds))
                except ValueError:
                    pass  # Invalid kind, ignore
            
            # Get symbols
            result = await session.execute(
                select(Symbol).where(and_(*filters)).order_by(Symbol.start_line)
            )
            symbols = result.scalars().all()
            
            if not symbols:
                return [TextContent(type="text", text=f"No symbols found in '{file_path}'")]
            
            # Group by kind
            by_kind = {}
            for symbol in symbols:
                kind = symbol.kind.value
                if kind not in by_kind:
                    by_kind[kind] = []
                by_kind[kind].append(symbol)
            
            # Format results
            formatted = [
                f"# Symbols in {file_path}\n",
                f"Total: {len(symbols)} symbols\n\n"
            ]
            
            for kind, syms in sorted(by_kind.items()):
                formatted.append(f"### {kind.upper()} ({len(syms)})\n\n")
                for symbol in syms:
                    formatted.append(
                        f"- **{symbol.name}** (Line {symbol.start_line})\n"
                    )
                    if symbol.signature:
                        formatted.append(f"  ```\n  {symbol.signature}\n  ```\n")
                    if symbol.documentation:
                        doc_preview = symbol.documentation[:100]
                        formatted.append(f"  {doc_preview}{'...' if len(symbol.documentation) > 100 else ''}\n")
                    formatted.append("\n")
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_list_symbols_in_file_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to list symbols: {str(e)}",
            )
        ]


async def list_dependencies(
    repository_id: int,
    dependency_type: Optional[str] = None,
    limit: int = 50,
) -> List[TextContent]:
    """
    List package dependencies.

    Args:
        repository_id: Repository ID
        dependency_type: Optional type filter (nuget, npm, etc.)
        limit: Maximum results

    Returns:
        List of dependencies
    """
    try:
        async with get_async_session() as session:
            from src.database.models import Dependency
            
            # Build query
            stmt = select(Dependency).where(Dependency.repository_id == repository_id)
            
            # Add dependency type filter
            if dependency_type:
                stmt = stmt.where(Dependency.dependency_type == dependency_type.lower())
            
            stmt = stmt.limit(limit)
            
            result = await session.execute(stmt)
            dependencies = result.scalars().all()
            
            if not dependencies:
                return [
                    TextContent(
                        type="text",
                        text=f"No dependencies found for repository ID {repository_id}",
                    )
                ]
            
            # Group by type
            nuget_deps = []
            npm_deps = []
            other_deps = []
            
            for dep in dependencies:
                dep_info = f"- **{dep.package_name}** v{dep.package_version or 'unknown'}{' (dev)' if dep.is_dev_dependency else ''} - {dep.file_path}\n"
                
                if dep.dependency_type == 'nuget':
                    nuget_deps.append(dep_info)
                elif dep.dependency_type == 'npm':
                    npm_deps.append(dep_info)
                else:
                    other_deps.append(dep_info)
            
            # Format results
            # Get repo name for header
            repo_result = await session.execute(select(Repository).where(Repository.id == repository_id))
            repo = repo_result.scalar_one_or_none()
            repo_name = repo.name if repo else f"ID {repository_id}"
            
            formatted = [f"Dependencies for repository: **{repo_name}**\n\n"]
            
            if nuget_deps:
                formatted.append(f"### NuGet Packages ({len(nuget_deps)})\n\n")
                formatted.extend(nuget_deps)
                formatted.append("\n")
            
            if npm_deps:
                formatted.append(f"### NPM Packages ({len(npm_deps)})\n\n")
                formatted.extend(npm_deps)
                formatted.append("\n")

            if other_deps:
                formatted.append(f"### Other Dependencies ({len(other_deps)})\n\n")
                formatted.extend(other_deps)
            
            return [TextContent(type="text", text="".join(formatted))]
            
    except Exception as e:
        logger.error("mcp_list_dependencies_failed", error=str(e), exc_info=True)
        return [
            TextContent(
                type="text",
                text=f"Failed to list dependencies: {str(e)}",
            )
        ]
