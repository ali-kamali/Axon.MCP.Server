import json
from typing import Any, Dict, List
from sqlalchemy import select, func

from src.database.models import File, Repository, Symbol
from src.database.session import get_async_session
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

async def list_mcp_resources() -> List[Dict[str, Any]]:
    """List available resources for HTTP transport."""
    try:
        async with get_async_session() as session:
            # Get repository statistics for resources
            result = await session.execute(select(Repository))
            repos = result.scalars().all()
            
            resources = []
            
            # Add repository overview resource
            resources.append({
                "uri": "axon://repositories/overview",
                "name": "Repository Overview",
                "description": "Overview of all indexed repositories with statistics",
                "mimeType": "application/json"
            })
            
            # Add individual repository resources
            for repo in repos:
                resources.append({
                    "uri": f"axon://repository/{repo.id}",
                    "name": f"Repository: {repo.name}",
                    "description": f"Detailed information about {repo.name} repository",
                    "mimeType": "application/json"
                })
                
                # Add repository file tree resource
                resources.append({
                    "uri": f"axon://repository/{repo.id}/files",
                    "name": f"Files: {repo.name}",
                    "description": f"File tree and structure of {repo.name}",
                    "mimeType": "application/json"
                })
            
            return resources
            
    except Exception as e:
        logger.error("mcp_list_resources_failed", error=str(e), exc_info=True)
        return []


async def read_mcp_resource(uri: str) -> Dict[str, Any]:
    """Read a specific resource for HTTP transport."""
    try:
        async with get_async_session() as session:
            if uri == "axon://repositories/overview":
                # Return repository overview
                result = await session.execute(select(Repository))
                repos = result.scalars().all()
                
                overview = {
                    "total_repositories": len(repos),
                    "repositories": [
                        {
                            "id": repo.id,
                            "name": repo.name,
                            "status": repo.status.value,
                            "total_files": repo.total_files,
                            "total_symbols": repo.total_symbols,
                            "last_synced": repo.last_synced_at.isoformat() if repo.last_synced_at else None,
                            "url": repo.url,
                            "default_branch": repo.default_branch
                        }
                        for repo in repos
                    ]
                }
                
                return {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(overview, indent=2)
                }
                
            elif uri.startswith("axon://repository/") and uri.endswith("/files"):
                # Extract repository ID
                repo_id = int(uri.split("/")[2])
                
                # Get repository files
                result = await session.execute(
                    select(File, Repository)
                    .join(Repository, File.repository_id == Repository.id)
                    .where(Repository.id == repo_id)
                )
                files_data = result.all()
                
                if not files_data:
                    raise ValueError(f"Repository {repo_id} not found")
                
                repo_name = files_data[0][1].name if files_data else "Unknown"
                
                # Get symbol counts per file (since File model doesn't have symbol_count attribute)
                file_ids = [file.id for file, _ in files_data]
                symbol_counts_result = await session.execute(
                    select(
                        Symbol.file_id,
                        func.count(Symbol.id).label('count')
                    )
                    .where(Symbol.file_id.in_(file_ids))
                    .group_by(Symbol.file_id)
                ) if file_ids else None
                symbol_counts = {row.file_id: row.count for row in symbol_counts_result} if symbol_counts_result else {}
                
                file_tree = {
                    "repository_id": repo_id,
                    "repository_name": repo_name,
                    "total_files": len(files_data),
                    "files": [
                        {
                            "id": file.id,
                            "path": file.path,
                            "language": file.language.value if file.language else None,
                            "size_bytes": file.size_bytes,
                            "symbol_count": symbol_counts.get(file.id, 0),
                            "last_modified": file.last_modified.isoformat() if file.last_modified else None
                        }
                        for file, _ in files_data
                    ]
                }
                
                return {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(file_tree, indent=2)
                }
                
            elif uri.startswith("axon://repository/"):
                # Extract repository ID
                repo_id = int(uri.split("/")[2])
                
                # Get repository details
                result = await session.execute(
                    select(Repository).where(Repository.id == repo_id)
                )
                repo = result.scalar_one_or_none()
                
                if not repo:
                    raise ValueError(f"Repository {repo_id} not found")
                
                # Get file statistics by language
                files_result = await session.execute(
                    select(File).where(File.repository_id == repo_id)
                )
                files = files_result.scalars().all()
                
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
                
                language_stats = {}
                for file in files:
                    lang = file.language.value if file.language else "unknown"
                    if lang not in language_stats:
                        language_stats[lang] = {"files": 0, "symbols": 0}
                    language_stats[lang]["files"] += 1
                    language_stats[lang]["symbols"] += symbol_counts.get(file.id, 0)
                
                repo_details = {
                    "id": repo.id,
                    "name": repo.name,
                    "url": repo.url,
                    "default_branch": repo.default_branch,
                    "status": repo.status.value,
                    "total_files": repo.total_files,
                    "total_symbols": repo.total_symbols,
                    "last_synced": repo.last_synced_at.isoformat() if repo.last_synced_at else None,
                    "created_at": repo.created_at.isoformat(),
                    "language_statistics": language_stats,
                    "description": f"Repository containing {repo.total_files} files with {repo.total_symbols} code symbols"
                }
                
                return {
                    "uri": uri,
                    "mimeType": "application/json", 
                    "text": json.dumps(repo_details, indent=2)
                }
            else:
                raise ValueError(f"Unknown resource URI: {uri}")
                
    except Exception as e:
        logger.error("mcp_read_resource_failed", uri=uri, error=str(e), exc_info=True)
        return {
            "uri": uri,
            "mimeType": "text/plain",
            "text": f"Error reading resource: {str(e)}"
        }
