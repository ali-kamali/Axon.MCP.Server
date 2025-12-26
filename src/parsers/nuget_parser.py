"""NuGet package parser for .NET dependency files."""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

from src.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class NuGetPackage:
    """Represents a NuGet package dependency."""
    package_name: str
    version: Optional[str] = None
    version_constraint: Optional[str] = None
    is_dev_dependency: bool = False
    file_path: str = ""
    dependency_type: str = "nuget"


class NuGetParser:
    """Parser for NuGet dependency files (.csproj, packages.config, Directory.Build.props)."""
    
    def parse_csproj(self, file_path: Path) -> List[NuGetPackage]:
        """
        Parse .csproj file for package references.
        
        Handles both old-style and SDK-style .csproj formats.
        
        Args:
            file_path: Path to .csproj file
            
        Returns:
            List of NuGetPackage objects
        """
        packages = []
        
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # SDK-style .csproj: <PackageReference Include="PackageName" Version="1.0.0" />
            for package_ref in root.findall(".//PackageReference"):
                package_name = package_ref.get("Include")
                if not package_name:
                    continue
                
                version = package_ref.get("Version")
                
                # Check if it's a development dependency
                is_dev = package_ref.get("PrivateAssets") == "All" or \
                         package_ref.get("IncludeAssets") == "runtime; build; native; contentfiles; analyzers"
                
                packages.append(NuGetPackage(
                    package_name=package_name,
                    version=version,
                    version_constraint=version,
                    is_dev_dependency=is_dev,
                    file_path=str(file_path),
                    dependency_type="nuget"
                ))
            
            # Old-style .csproj: <Reference Include="PackageName, Version=1.0.0, ..." />
            # These are typically GAC references, not NuGet packages
            # We'll skip these for now as they're not package dependencies
            
            logger.debug(
                "parsed_csproj",
                file_path=str(file_path),
                packages_found=len(packages)
            )
            
        except ET.ParseError as e:
            logger.warning(
                "failed_to_parse_csproj",
                file_path=str(file_path),
                error=str(e)
            )
        except Exception as e:
            logger.error(
                "error_parsing_csproj",
                file_path=str(file_path),
                error=str(e)
            )
        
        return packages
    
    def parse_packages_config(self, file_path: Path) -> List[NuGetPackage]:
        """
        Parse packages.config file for package references.
        
        Format: <package id="PackageName" version="1.0.0" targetFramework="net48" />
        
        Args:
            file_path: Path to packages.config file
            
        Returns:
            List of NuGetPackage objects
        """
        packages = []
        
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            for package in root.findall(".//package"):
                package_name = package.get("id")
                version = package.get("version")
                
                if not package_name:
                    continue
                
                # packages.config doesn't distinguish dev dependencies
                # We could check if it's in a "development" category, but that's not standard
                
                packages.append(NuGetPackage(
                    package_name=package_name,
                    version=version,
                    version_constraint=version,
                    is_dev_dependency=False,
                    file_path=str(file_path),
                    dependency_type="nuget"
                ))
            
            logger.debug(
                "parsed_packages_config",
                file_path=str(file_path),
                packages_found=len(packages)
            )
            
        except ET.ParseError as e:
            logger.warning(
                "failed_to_parse_packages_config",
                file_path=str(file_path),
                error=str(e)
            )
        except Exception as e:
            logger.error(
                "error_parsing_packages_config",
                file_path=str(file_path),
                error=str(e)
            )
        
        return packages
    
    def parse_directory_build_props(self, file_path: Path) -> List[NuGetPackage]:
        """
        Parse Directory.Build.props for centralized package management.
        
        Format: <PackageReference Include="PackageName" Version="1.0.0" />
        
        Args:
            file_path: Path to Directory.Build.props file
            
        Returns:
            List of NuGetPackage objects
        """
        # Directory.Build.props has the same format as .csproj for PackageReference
        # We can reuse the same parsing logic
        return self.parse_csproj(file_path)
    
    def parse_file(self, file_path: Path) -> List[NuGetPackage]:
        """
        Parse any NuGet dependency file based on its name.
        
        Args:
            file_path: Path to dependency file
            
        Returns:
            List of NuGetPackage objects
        """
        file_name = file_path.name.lower()
        
        if file_name.endswith('.csproj'):
            return self.parse_csproj(file_path)
        elif file_name == 'packages.config':
            return self.parse_packages_config(file_path)
        elif file_name in ('directory.build.props', 'directory.packages.props'):
            return self.parse_directory_build_props(file_path)
        else:
            logger.warning(
                "unknown_nuget_file_type",
                file_path=str(file_path)
            )
            return []
