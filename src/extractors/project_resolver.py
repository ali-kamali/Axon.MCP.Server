"""
Project resolver to map files to their containing projects.
Handles path normalization for Docker environments.
"""
from pathlib import Path
from typing import Optional, Dict, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models import Project, Repository
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

class ProjectResolver:
    """
    Maps files to their containing projects based on path analysis.
    Handles Docker container absolute paths vs repository-relative file paths.
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self._cache: Dict[str, Optional[int]] = {}
        self._repo_path_cache: Dict[int, str] = {}  # Cache for repository paths
    
    async def get_project_for_file(
        self,
        file_path: str,
        repository_id: int
    ) -> Optional[int]:
        """
        Get the project ID that contains a given file.
        
        Key understanding:
        - file_path is RELATIVE to repo root (e.g., 'src/Api/Controllers/UserController.cs')
        - Project.file_path is ABSOLUTE Docker path (e.g., '/app/cache/repos/provider/org/repo/src/Api/Axon.Api.csproj')
        - Repository.path contains the org/repo path (e.g., 'Axon.Health/Axon.Health.HcpCatalog')
        
        Args:
            file_path: Path to the file (relative to repository root)
            repository_id: Repository ID
            
        Returns:
            project_id if found, None otherwise
        """
        # Check cache
        cache_key = f"{repository_id}:{file_path}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Get repository path (to know how many parts to skip)
        repo_path = await self._get_repository_path(repository_id)
        if not repo_path:
            logger.warning(f"Could not find repository path for repo_id={repository_id}")
            return None
        
        # Get all projects for this repository
        query = select(Project).where(Project.repository_id == repository_id)
        result = await self.session.execute(query)
        projects = result.scalars().all()
        
        if not projects:
            logger.debug("no_projects_found", repository_id=repository_id)
            self._cache[cache_key] = None
            return None
        
        logger.debug(f"Resolving project for file: '{file_path}' in repo {repository_id} (path: {repo_path})")
        
        # Find the project that contains this file
        project_id = self._find_containing_project(file_path, projects, repo_path)
        
        # Cache result
        self._cache[cache_key] = project_id
        
        if project_id:
            logger.info(
                "file_mapped_to_project",
                file_path=file_path,
                project_id=project_id
            )
        else:
            logger.warning(
                "file_not_in_project",
                file_path=file_path,
                repository_id=repository_id
            )
        
        return project_id
    
    async def _get_repository_path(self, repository_id: int) -> Optional[str]:
        """Get the repository path from the Repository table."""
        if repository_id in self._repo_path_cache:
            return self._repo_path_cache[repository_id]
        
        result = await self.session.execute(
            select(Repository.path_with_namespace).where(Repository.id == repository_id)
        )
        repo_path = result.scalar_one_or_none()
        
        if repo_path:
            self._repo_path_cache[repository_id] = repo_path
        
        return repo_path
    
    def _find_containing_project(
        self,
        file_path: str,
        projects: List[Project],
        repo_path: str
    ) -> Optional[int]:
        """
        Find which project contains the file.
        
        Strategy:
        1. For each project, extract its directory relative to repo root
        2. Check if file path is inside that project directory
        3. Return the most specific (deepest) match
        
        Args:
            file_path: File path (relative to repo root, e.g., 'Axon.Health.HcpCatalogueService.Api/Controllers/UserController.cs')
            projects: List of projects (with absolute Docker paths)
            repo_path: Repository path from Repository.path (e.g., 'Axon.Health/Axon.Health.HcpCatalog')
            
        Returns:
            project_id of containing project, or None
        """
        file_path_norm = Path(file_path)
        
        # Count how many parts are in the repository path
        # e.g., 'Axon.Health/Axon.Health.HcpCatalog' has 2 parts
        repo_path_parts_count = len(Path(repo_path).parts)
        
        matches = []
        
        for project in projects:
            try:
                # Example project.file_path:
                # '/app/cache/repos/azuredevops/Axon.Health/Axon.Health.HcpCatalog/Axon.Health.HcpCatalogueService.Api/Axon.Health.HcpCatalogueService.Api.csproj'
                #  ^-repos index---^provider   ^-----repo path (2 parts)-------------^  ^---relative to repo root-------------^
                
                project_abs_path = Path(project.file_path)
                project_dir = project_abs_path.parent  # Directory containing .csproj
                
                # Normalize to relative path
                project_relative = self._normalize_project_path(project_dir, repo_path_parts_count)
                
                if not project_relative:
                    logger.warning(f"Could not normalize path for project {project.name}: {project_dir}")
                    continue
                
                logger.debug(f"  Project '{project.name}': {project_relative}")
                
                # Check if file is inside this project directory
                if self._is_file_in_directory(file_path_norm, Path(project_relative)):
                    depth = len(Path(project_relative).parts)
                    matches.append((project.id, depth, project.name, project_relative))
                    logger.debug(f"    ✓ MATCH (depth={depth})")
                    
            except Exception as e:
                logger.error(f"Error processing project {project.name}: {e}", exc_info=True)
                continue
        
        if not matches:
            logger.warning(f"No matching project found for file: {file_path}")
            return None
        
        # Return the deepest (most specific) match
        matches.sort(key=lambda x: x[1], reverse=True)
        best = matches[0]
        logger.info(f"✓ File '{file_path}' → Project '{best[2]}' (id={best[0]}, dir='{best[3]}')") 
        return best[0]
    
    def _normalize_project_path(self, project_dir: Path, repo_path_parts_count: int) -> Optional[str]:
        """
        Convert absolute Docker path to relative path.
        
        Input:  /app/cache/repos/azuredevops/Axon.Health/Axon.Health.HcpCatalog/Axon.Health.HcpCatalogueService.Api
        Repo parts: 2 (Axon.Health, Axon.Health.HcpCatalog)
        Output: Axon.Health.HcpCatalogueService.Api
        """
        parts = project_dir.parts
        
        # Find 'repos' in the path
        if 'repos' not in parts:
            logger.warning(f"Could not find 'repos' in project path: {project_dir}")
            return None
        
        repos_index = parts.index('repos')
        # Skip: /app/cache/repos/<provider>/<repo_path_parts>/
        # repos_index + 1 = provider (e.g., azuredevops)
        # repos_index + 2 = start of repo path (e.g., Axon.Health)
        # repos_index + 2 + repo_path_parts_count = start of relative path
        start_index = repos_index + 2 + repo_path_parts_count
        
        if start_index < len(parts):
            relative_parts = parts[start_index:]
            return str(Path(*relative_parts))
        
        logger.warning(f"Not enough parts in project path: {project_dir}, start_index={start_index}, len={len(parts)}")
        return None
    
    def _is_file_in_directory(self, file_path: Path, dir_path: Path) -> bool:
        """
        Check if file_path is inside dir_path.
        
        Both paths should be relative.
        """
        try:
            # This will raise ValueError if file_path is not relative to dir_path
            file_path.relative_to(dir_path)
            return True
        except ValueError:
            return False
    
    async def get_project_metadata(
        self,
        project_id: int
    ) -> Optional[Dict]:
        """
        Get project metadata for a given project_id.
        
        Args:
            project_id: Project ID
            
        Returns:
            Dictionary with project metadata
        """
        query = select(Project).where(Project.id == project_id)
        result = await self.session.execute(query)
        project = result.scalar_one_or_none()
        
        if not project:
            return None
        
        return {
            'id': project.id,
            'name': project.name,
            'assembly_name': project.root_namespace,
            'target_framework': project.target_framework,
            'project_type': project.project_type
        }
    
    def clear_cache(self):
        """Clear the project resolution cache."""
        self._cache.clear()
        self._repo_path_cache.clear()
