"""Python package parser for Python dependency files."""

import re
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

from src.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class PythonPackage:
    """Represents a Python package dependency."""
    package_name: str
    version: Optional[str] = None
    version_constraint: Optional[str] = None
    is_dev_dependency: bool = False
    file_path: str = ""
    dependency_type: str = "pip"


class PythonDependencyParser:
    """Parser for Python dependency files (requirements.txt, pyproject.toml, Pipfile)."""
    
    def parse_requirements_txt(self, file_path: Path) -> List[PythonPackage]:
        """
        Parse requirements.txt for package dependencies.
        
        Supports formats:
        - package==1.0.0
        - package>=1.0.0
        - package~=1.0.0
        - package
        - package[extra]==1.0.0
        
        Args:
            file_path: Path to requirements.txt file
            
        Returns:
            List of PythonPackage objects
        """
        packages = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            for line in lines:
                line = line.strip()
                
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                
                # Skip -r, -c, -e flags (requirements file includes, constraints, editable)
                if line.startswith(('-r ', '-c ', '-e ', '--')):
                    continue
                
                # Parse package specification
                # Pattern: package_name[extras]version_spec
                match = re.match(r'^([a-zA-Z0-9_\-\.]+)(\[[^\]]+\])?(.*)', line)
                if not match:
                    continue
                
                package_name = match.group(1)
                extras = match.group(2) or ''
                version_spec = match.group(3).strip()
                
                # Extract version if present
                version = None
                version_constraint = version_spec if version_spec else None
                
                # Try to extract exact version from ==
                if '==' in version_spec:
                    version = version_spec.split('==')[1].strip()
                
                packages.append(PythonPackage(
                    package_name=package_name,
                    version=version,
                    version_constraint=version_constraint,
                    is_dev_dependency=False,  # requirements.txt doesn't distinguish
                    file_path=str(file_path),
                    dependency_type="pip"
                ))
            
            logger.debug(
                "parsed_requirements_txt",
                file_path=str(file_path),
                packages_found=len(packages)
            )
            
        except Exception as e:
            logger.error(
                "error_parsing_requirements_txt",
                file_path=str(file_path),
                error=str(e)
            )
        
        return packages
    
    def parse_pyproject_toml(self, file_path: Path) -> List[PythonPackage]:
        """
        Parse pyproject.toml for package dependencies.
        
        Supports Poetry and PEP 621 formats.
        
        Args:
            file_path: Path to pyproject.toml file
            
        Returns:
            List of PythonPackage objects
        """
        packages = []
        
        try:
            # Try to import tomli/tomllib for TOML parsing
            try:
                import tomllib  # Python 3.11+
            except ImportError:
                try:
                    import tomli as tomllib  # Fallback for older Python
                except ImportError:
                    logger.warning(
                        "toml_library_not_available",
                        file_path=str(file_path),
                        message="Install tomli to parse pyproject.toml files"
                    )
                    return packages
            
            with open(file_path, 'rb') as f:
                data = tomllib.load(f)
            
            # PEP 621 format: [project.dependencies]
            if 'project' in data and 'dependencies' in data['project']:
                for dep_spec in data['project']['dependencies']:
                    package = self._parse_pep_508_string(dep_spec, str(file_path))
                    if package:
                        packages.append(package)
            
            # PEP 621 optional dependencies (dev)
            if 'project' in data and 'optional-dependencies' in data['project']:
                for group_name, deps in data['project']['optional-dependencies'].items():
                    is_dev = group_name in ('dev', 'test', 'tests', 'development')
                    for dep_spec in deps:
                        package = self._parse_pep_508_string(dep_spec, str(file_path), is_dev)
                        if package:
                            packages.append(package)
            
            # Poetry format: [tool.poetry.dependencies]
            if 'tool' in data and 'poetry' in data['tool']:
                poetry = data['tool']['poetry']
                
                # Regular dependencies
                if 'dependencies' in poetry:
                    for package_name, version_spec in poetry['dependencies'].items():
                        if package_name == 'python':  # Skip Python version
                            continue
                        
                        # Handle dict format: {version = "^1.0.0"}
                        if isinstance(version_spec, dict):
                            version_spec = version_spec.get('version', '')
                        
                        packages.append(PythonPackage(
                            package_name=package_name,
                            version_constraint=str(version_spec),
                            is_dev_dependency=False,
                            file_path=str(file_path),
                            dependency_type="pip"
                        ))
                
                # Dev dependencies
                if 'dev-dependencies' in poetry or 'group' in poetry:
                    dev_deps = poetry.get('dev-dependencies', {})
                    
                    # Poetry 1.2+ group format
                    if 'group' in poetry:
                        for group_name, group_data in poetry['group'].items():
                            if 'dependencies' in group_data:
                                dev_deps.update(group_data['dependencies'])
                    
                    for package_name, version_spec in dev_deps.items():
                        if isinstance(version_spec, dict):
                            version_spec = version_spec.get('version', '')
                        
                        packages.append(PythonPackage(
                            package_name=package_name,
                            version_constraint=str(version_spec),
                            is_dev_dependency=True,
                            file_path=str(file_path),
                            dependency_type="pip"
                        ))
            
            logger.debug(
                "parsed_pyproject_toml",
                file_path=str(file_path),
                packages_found=len(packages)
            )
            
        except Exception as e:
            logger.error(
                "error_parsing_pyproject_toml",
                file_path=str(file_path),
                error=str(e)
            )
        
        return packages
    
    def parse_pipfile(self, file_path: Path) -> List[PythonPackage]:
        """
        Parse Pipfile for package dependencies.
        
        Pipfile uses TOML format with [packages] and [dev-packages] sections.
        
        Args:
            file_path: Path to Pipfile
            
        Returns:
            List of PythonPackage objects
        """
        packages = []
        
        try:
            # Try to import tomli/tomllib for TOML parsing
            try:
                import tomllib  # Python 3.11+
            except ImportError:
                try:
                    import tomli as tomllib  # Fallback
                except ImportError:
                    logger.warning(
                        "toml_library_not_available",
                        file_path=str(file_path),
                        message="Install tomli to parse Pipfile"
                    )
                    return packages
            
            with open(file_path, 'rb') as f:
                data = tomllib.load(f)
            
            # Parse [packages]
            if 'packages' in data:
                for package_name, version_spec in data['packages'].items():
                    # Handle dict format: {version = "==1.0.0"}
                    if isinstance(version_spec, dict):
                        version_spec = version_spec.get('version', '*')
                    
                    packages.append(PythonPackage(
                        package_name=package_name,
                        version_constraint=str(version_spec),
                        is_dev_dependency=False,
                        file_path=str(file_path),
                        dependency_type="pip"
                    ))
            
            # Parse [dev-packages]
            if 'dev-packages' in data:
                for package_name, version_spec in data['dev-packages'].items():
                    if isinstance(version_spec, dict):
                        version_spec = version_spec.get('version', '*')
                    
                    packages.append(PythonPackage(
                        package_name=package_name,
                        version_constraint=str(version_spec),
                        is_dev_dependency=True,
                        file_path=str(file_path),
                        dependency_type="pip"
                    ))
            
            logger.debug(
                "parsed_pipfile",
                file_path=str(file_path),
                packages_found=len(packages)
            )
            
        except Exception as e:
            logger.error(
                "error_parsing_pipfile",
                file_path=str(file_path),
                error=str(e)
            )
        
        return packages
    
    def _parse_pep_508_string(self, dep_spec: str, file_path: str, is_dev: bool = False) -> Optional[PythonPackage]:
        """
        Parse a PEP 508 dependency specification string.
        
        Format: package_name[extras] (>=1.0.0,<2.0.0) ; python_version >= "3.8"
        
        Args:
            dep_spec: PEP 508 dependency specification
            file_path: Source file path
            is_dev: Whether this is a dev dependency
            
        Returns:
            PythonPackage object or None
        """
        # Remove environment markers (after semicolon)
        if ';' in dep_spec:
            dep_spec = dep_spec.split(';')[0].strip()
        
        # Parse package name and version
        match = re.match(r'^([a-zA-Z0-9_\-\.]+)(\[[^\]]+\])?\s*(.*)$', dep_spec)
        if not match:
            return None
        
        package_name = match.group(1)
        version_spec = match.group(3).strip()
        
        # Remove parentheses from version spec
        version_spec = version_spec.strip('()')
        
        return PythonPackage(
            package_name=package_name,
            version_constraint=version_spec if version_spec else None,
            is_dev_dependency=is_dev,
            file_path=file_path,
            dependency_type="pip"
        )
    
    def parse_file(self, file_path: Path) -> List[PythonPackage]:
        """
        Parse any Python dependency file based on its name.
        
        Args:
            file_path: Path to dependency file
            
        Returns:
            List of PythonPackage objects
        """
        file_name = file_path.name.lower()
        
        if file_name == 'requirements.txt' or file_name.endswith('-requirements.txt'):
            return self.parse_requirements_txt(file_path)
        elif file_name == 'pyproject.toml':
            return self.parse_pyproject_toml(file_path)
        elif file_name == 'pipfile':
            return self.parse_pipfile(file_path)
        else:
            logger.warning(
                "unknown_python_file_type",
                file_path=str(file_path)
            )
            return []
