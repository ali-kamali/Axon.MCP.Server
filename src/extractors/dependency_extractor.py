"""Dependency extractor for indexing package dependencies."""

from pathlib import Path
import os
from typing import List, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from src.database.models import Dependency, Repository
from src.parsers.nuget_parser import NuGetParser, NuGetPackage
from src.parsers.npm_parser import NpmParser, NpmPackage
from src.parsers.python_dependency_parser import PythonDependencyParser, PythonPackage
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class DependencyExtractor:
    """Extracts and indexes package dependencies from various package managers."""
    
    # Dependency file patterns to search for
    DEPENDENCY_FILES = {
        'nuget': ['.csproj', 'packages.config', 'Directory.Build.props', 'Directory.Packages.props'],
        'npm': ['package.json', 'package-lock.json'],
        'python': ['requirements.txt', 'pyproject.toml', 'Pipfile'],
    }
    
    def __init__(self, session: AsyncSession):
        """
        Initialize dependency extractor.
        
        Args:
            session: Database session
        """
        self.session = session
        self.nuget_parser = NuGetParser()
        self.npm_parser = NpmParser()
        self.python_parser = PythonDependencyParser()
    
    async def extract_dependencies(self, repository_id: int, repo_path: Path) -> int:
        """
        Extract all dependencies from a repository.
        
        Args:
            repository_id: Repository ID
            repo_path: Path to repository root
            
        Returns:
            Number of dependencies found
        """
        logger.info(
            "dependency_extraction_started",
            repository_id=repository_id,
            repo_path=str(repo_path)
        )
        
        # Clear existing dependencies for this repository
        await self._clear_existing_dependencies(repository_id)
        
        # Detect all dependency files
        dependency_files = self._detect_dependency_files(repo_path)
        
        logger.debug(
            "dependency_files_detected",
            repository_id=repository_id,
            files_found=len(dependency_files)
        )
        
        # Parse and store dependencies
        total_dependencies = 0
        for file_path in dependency_files:
            count = await self._parse_and_store(file_path, repository_id, repo_path)
            total_dependencies += count
        
        # Commit all changes
        await self.session.commit()
        
        logger.info(
            "dependency_extraction_completed",
            repository_id=repository_id,
            dependencies_found=total_dependencies,
            files_processed=len(dependency_files)
        )
        
        return total_dependencies
    
    def _detect_dependency_files(self, repo_path: Path) -> List[Path]:
        """
        Detect all dependency files in the repository.
        
        Args:
            repo_path: Path to repository root
            
        Returns:
            List of dependency file paths
        """
        dependency_files = []
        
        # Walk through repository
        for root, dirs, files in os.walk(repo_path):
            root_path = Path(root)
            # Skip common directories to ignore
            dirs[:] = [d for d in dirs if d not in {
                'node_modules', '.git', '.venv', 'venv', 'env',
                '__pycache__', 'bin', 'obj', 'dist', 'build',
                '.pytest_cache', '.mypy_cache', '.tox'
            }]
            
            for file in files:
                file_path = root_path / file
                file_name = file.lower()
                
                # Check if it's a dependency file
                if self._is_dependency_file(file_name):
                    dependency_files.append(file_path)
        
        return dependency_files
    
    def _is_dependency_file(self, file_name: str) -> bool:
        """
        Check if a file is a dependency file.
        
        Args:
            file_name: File name (lowercase)
            
        Returns:
            True if it's a dependency file
        """
        # NuGet files
        if file_name.endswith('.csproj') or file_name in {
            'packages.config', 'directory.build.props', 'directory.packages.props'
        }:
            return True
        
        # npm files
        if file_name in {'package.json', 'package-lock.json'}:
            return True
        
        # Python files
        if file_name in {'requirements.txt', 'pyproject.toml', 'pipfile'} or \
           file_name.endswith('-requirements.txt'):
            return True
        
        return False
    
    async def _parse_and_store(
        self,
        file_path: Path,
        repository_id: int,
        repo_path: Path
    ) -> int:
        """
        Parse a dependency file and store results in database.
        
        Args:
            file_path: Path to dependency file
            repository_id: Repository ID
            repo_path: Repository root path
            
        Returns:
            Number of dependencies stored
        """
        try:
            # Determine parser based on file type
            file_name = file_path.name.lower()
            packages = []
            
            if file_name.endswith('.csproj') or file_name in {
                'packages.config', 'directory.build.props', 'directory.packages.props'
            }:
                packages = self.nuget_parser.parse_file(file_path)
                
            elif file_name in {'package.json', 'package-lock.json'}:
                # Only parse package.json if package-lock.json doesn't exist
                # to avoid duplicates
                if file_name == 'package.json':
                    lock_file = file_path.parent / 'package-lock.json'
                    if lock_file.exists():
                        logger.debug(
                            "skipping_package_json",
                            file_path=str(file_path),
                            reason="package-lock.json exists"
                        )
                        return 0
                
                packages = self.npm_parser.parse_file(file_path)
                
            elif file_name in {'requirements.txt', 'pyproject.toml', 'pipfile'} or \
                 file_name.endswith('-requirements.txt'):
                packages = self.python_parser.parse_file(file_path)
            
            # Store packages in database
            if packages:
                # Get relative path from repo root
                try:
                    relative_path = file_path.relative_to(repo_path)
                except ValueError:
                    relative_path = file_path
                
                for package in packages:
                    dependency = Dependency(
                        repository_id=repository_id,
                        package_name=package.package_name,
                        package_version=package.version,
                        version_constraint=package.version_constraint,
                        dependency_type=package.dependency_type,
                        is_dev_dependency=1 if package.is_dev_dependency else 0,
                        is_transitive=1 if getattr(package, 'is_transitive', False) else 0,
                        file_path=str(relative_path)
                    )
                    self.session.add(dependency)
                
                logger.debug(
                    "dependencies_stored",
                    file_path=str(file_path),
                    packages_stored=len(packages)
                )
                
                return len(packages)
            
        except Exception as e:
            logger.error(
                "error_parsing_dependency_file",
                file_path=str(file_path),
                error=str(e)
            )
        
        return 0
    
    async def _clear_existing_dependencies(self, repository_id: int):
        """
        Clear existing dependencies for a repository.
        
        Args:
            repository_id: Repository ID
        """
        try:
            await self.session.execute(
                delete(Dependency).where(Dependency.repository_id == repository_id)
            )
            logger.debug(
                "cleared_existing_dependencies",
                repository_id=repository_id
            )
        except Exception as e:
            logger.error(
                "error_clearing_dependencies",
                repository_id=repository_id,
                error=str(e)
            )
