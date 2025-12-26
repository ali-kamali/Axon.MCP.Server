"""npm package parser for Node.js dependency files."""

import json
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

from src.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class NpmPackage:
    """Represents an npm package dependency."""
    package_name: str
    version: Optional[str] = None
    version_constraint: Optional[str] = None
    is_dev_dependency: bool = False
    is_transitive: bool = False
    file_path: str = ""
    dependency_type: str = "npm"


class NpmParser:
    """Parser for npm dependency files (package.json, package-lock.json)."""
    
    def parse_package_json(self, file_path: Path) -> List[NpmPackage]:
        """
        Parse package.json for dependencies and devDependencies.
        
        Args:
            file_path: Path to package.json file
            
        Returns:
            List of NpmPackage objects
        """
        packages = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Parse regular dependencies
            dependencies = data.get('dependencies', {})
            for package_name, version_constraint in dependencies.items():
                packages.append(NpmPackage(
                    package_name=package_name,
                    version_constraint=version_constraint,
                    is_dev_dependency=False,
                    is_transitive=False,
                    file_path=str(file_path),
                    dependency_type="npm"
                ))
            
            # Parse dev dependencies
            dev_dependencies = data.get('devDependencies', {})
            for package_name, version_constraint in dev_dependencies.items():
                packages.append(NpmPackage(
                    package_name=package_name,
                    version_constraint=version_constraint,
                    is_dev_dependency=True,
                    is_transitive=False,
                    file_path=str(file_path),
                    dependency_type="npm"
                ))
            
            # Optionally parse peerDependencies and optionalDependencies
            peer_dependencies = data.get('peerDependencies', {})
            for package_name, version_constraint in peer_dependencies.items():
                packages.append(NpmPackage(
                    package_name=package_name,
                    version_constraint=version_constraint,
                    is_dev_dependency=False,
                    is_transitive=False,
                    file_path=str(file_path),
                    dependency_type="npm"
                ))
            
            logger.debug(
                "parsed_package_json",
                file_path=str(file_path),
                packages_found=len(packages),
                dependencies=len(dependencies),
                dev_dependencies=len(dev_dependencies),
                peer_dependencies=len(peer_dependencies)
            )
            
        except json.JSONDecodeError as e:
            logger.warning(
                "failed_to_parse_package_json",
                file_path=str(file_path),
                error=str(e)
            )
        except Exception as e:
            logger.error(
                "error_parsing_package_json",
                file_path=str(file_path),
                error=str(e)
            )
        
        return packages
    
    def parse_package_lock(self, file_path: Path, max_transitive_depth: int = 2) -> List[NpmPackage]:
        """
        Parse package-lock.json for exact versions and transitive dependencies.
        
        Note: package-lock.json can be very large. We limit transitive depth to avoid
        storing thousands of indirect dependencies.
        
        Args:
            file_path: Path to package-lock.json file
            max_transitive_depth: Maximum depth for transitive dependencies (default: 2)
            
        Returns:
            List of NpmPackage objects
        """
        packages = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # package-lock.json v2+ format
            if 'packages' in data:
                packages_data = data['packages']
                
                # Root package (empty key "")
                root_deps = packages_data.get('', {}).get('dependencies', {})
                root_dev_deps = packages_data.get('', {}).get('devDependencies', {})
                
                for package_path, package_info in packages_data.items():
                    if not package_path:  # Skip root
                        continue
                    
                    # Extract package name from path (e.g., "node_modules/package-name")
                    package_name = package_path.split('node_modules/')[-1]
                    version = package_info.get('version')
                    
                    # Determine if it's a dev dependency
                    is_dev = package_name in root_dev_deps
                    
                    # Determine if it's transitive (depth > 1)
                    depth = package_path.count('node_modules/') - 1
                    is_transitive = depth > 0
                    
                    # Skip deep transitive dependencies
                    if depth > max_transitive_depth:
                        continue
                    
                    packages.append(NpmPackage(
                        package_name=package_name,
                        version=version,
                        version_constraint=version,
                        is_dev_dependency=is_dev,
                        is_transitive=is_transitive,
                        file_path=str(file_path),
                        dependency_type="npm"
                    ))
            
            # package-lock.json v1 format
            elif 'dependencies' in data:
                def extract_deps(deps_dict: Dict, is_dev: bool = False, depth: int = 0):
                    """Recursively extract dependencies from v1 format."""
                    if depth > max_transitive_depth:
                        return
                    
                    for package_name, package_info in deps_dict.items():
                        version = package_info.get('version')
                        
                        packages.append(NpmPackage(
                            package_name=package_name,
                            version=version,
                            version_constraint=version,
                            is_dev_dependency=is_dev,
                            is_transitive=(depth > 0),
                            file_path=str(file_path),
                            dependency_type="npm"
                        ))
                        
                        # Recursively process nested dependencies
                        nested_deps = package_info.get('dependencies', {})
                        if nested_deps:
                            extract_deps(nested_deps, is_dev, depth + 1)
                
                extract_deps(data.get('dependencies', {}))
            
            logger.debug(
                "parsed_package_lock",
                file_path=str(file_path),
                packages_found=len(packages)
            )
            
        except json.JSONDecodeError as e:
            logger.warning(
                "failed_to_parse_package_lock",
                file_path=str(file_path),
                error=str(e)
            )
        except Exception as e:
            logger.error(
                "error_parsing_package_lock",
                file_path=str(file_path),
                error=str(e)
            )
        
        return packages
    
    def parse_file(self, file_path: Path) -> List[NpmPackage]:
        """
        Parse any npm dependency file based on its name.
        
        Args:
            file_path: Path to dependency file
            
        Returns:
            List of NpmPackage objects
        """
        file_name = file_path.name.lower()
        
        if file_name == 'package.json':
            return self.parse_package_json(file_path)
        elif file_name == 'package-lock.json':
            return self.parse_package_lock(file_path)
        else:
            logger.warning(
                "unknown_npm_file_type",
                file_path=str(file_path)
            )
            return []
