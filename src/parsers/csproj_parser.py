"""Parser for .csproj (C# project) files."""

import xml.etree.ElementTree as ET
from typing import List, Optional
from pathlib import Path
from src.config.enums import LanguageEnum, SymbolKindEnum
from src.parsers.base_parser import BaseParser, ParseResult, ParsedSymbol


class CsProjParser(BaseParser):
    """Parser for .csproj project files."""
    
    def __init__(self):
        self.language = LanguageEnum.CSHARP
    
    def get_language(self) -> LanguageEnum:
        """Return the language this parser handles."""
        return self.language
    
    def is_supported(self, file_path: Path) -> bool:
        """Check if file is a .csproj file."""
        return file_path.suffix.lower() == '.csproj'
    
    def parse(self, code: str, file_path: Optional[str] = None) -> ParseResult:
        """
        Parse .csproj file and extract:
        - Package references (NuGet packages)
        - Project references
        - Target framework
        - Output type
        - Project properties
        """
        import time
        start_time = time.time()
        
        symbols = []
        imports = []  # Store project references as imports
        errors = []
        
        try:
            # Parse XML
            root = ET.fromstring(code)
            
            # Extract package references
            symbols.extend(self._extract_package_references(root, file_path))
            
            # Extract project references
            project_refs = self._extract_project_references(root, file_path)
            symbols.extend(project_refs)
            imports.extend([ref.name for ref in project_refs])
            
            # Extract project properties
            symbols.extend(self._extract_project_properties(root, file_path))
            
        except ET.ParseError as e:
            errors.append(f"XML parsing error: {str(e)}")
        except Exception as e:
            errors.append(f"CsProj parsing error: {str(e)}")
        
        duration_ms = (time.time() - start_time) * 1000
        
        return ParseResult(
            language=self.language,
            file_path=file_path or "unknown",
            symbols=symbols,
            imports=imports,
            exports=[],
            parse_errors=errors,
            parse_duration_ms=duration_ms
        )
    
    def _extract_package_references(self, root: ET.Element, file_path: Optional[str]) -> List[ParsedSymbol]:
        """Extract NuGet package references."""
        symbols = []
        
        # Find all PackageReference elements
        for pkg_ref in root.findall('.//PackageReference'):
            name = pkg_ref.get('Include', 'Unknown')
            version = pkg_ref.get('Version', 'unknown')
            
            # Check for PrivateAssets (indicates dev dependency)
            private_assets = pkg_ref.get('PrivateAssets', '')
            is_dev = 'all' in private_assets.lower()
            
            symbols.append(ParsedSymbol(
                kind=SymbolKindEnum.CONSTANT,  # Using CONSTANT to represent packages
                name=name,
                start_line=0,
                end_line=0,
                start_column=0,
                end_column=0,
                signature=f"PackageReference: {name} v{version}",
                documentation=f"NuGet package dependency{' (dev)' if is_dev else ''}",
                structured_docs={
                    'type': 'nuget_package',
                    'version': version,
                    'is_dev_dependency': is_dev
                }
            ))
        
        return symbols
    
    def _extract_project_references(self, root: ET.Element, file_path: Optional[str]) -> List[ParsedSymbol]:
        """Extract project references."""
        symbols = []
        
        # Find all ProjectReference elements
        for proj_ref in root.findall('.//ProjectReference'):
            path = proj_ref.get('Include', 'Unknown')
            
            # Extract project name from path
            name = Path(path).stem if path else 'Unknown'
            
            symbols.append(ParsedSymbol(
                kind=SymbolKindEnum.MODULE,  # Using MODULE for project references
                name=name,
                start_line=0,
                end_line=0,
                start_column=0,
                end_column=0,
                signature=f"ProjectReference: {name}",
                documentation=f"Project dependency at {path}",
                structured_docs={
                    'type': 'project_reference',
                    'path': path
                }
            ))
        
        return symbols
    
    def _extract_project_properties(self, root: ET.Element, file_path: Optional[str]) -> List[ParsedSymbol]:
        """
        Extract important project properties from PropertyGroup.
        
        Phase 2.2: Enhanced to extract compilation context:
        - DefineConstants
        - LangVersion
        - Nullable
        - RootNamespace
        - AssemblyName
        - TargetFramework
        - OutputType
        """
        symbols = []
        
        # Collect all PropertyGroup settings
        project_metadata = {
            'target_framework': None,
            'output_type': None,
            'assembly_name': None,
            'root_namespace': None,
            'define_constants': [],
            'lang_version': None,
            'nullable': None,
        }
        
        # Find PropertyGroup elements
        for prop_group in root.findall('.//PropertyGroup'):
            # Target Framework
            target_fw = prop_group.find('TargetFramework')
            if target_fw is not None and target_fw.text:
                project_metadata['target_framework'] = target_fw.text
            
            # Output Type
            output_type = prop_group.find('OutputType')
            if output_type is not None and output_type.text:
                project_metadata['output_type'] = output_type.text
            
            # Assembly Name
            assembly_name = prop_group.find('AssemblyName')
            if assembly_name is not None and assembly_name.text:
                project_metadata['assembly_name'] = assembly_name.text
            
            # Root Namespace (Phase 2.2)
            root_ns = prop_group.find('RootNamespace')
            if root_ns is not None and root_ns.text:
                project_metadata['root_namespace'] = root_ns.text
            
            # DefineConstants (Phase 2.2)
            define_const = prop_group.find('DefineConstants')
            if define_const is not None and define_const.text:
                # Split by semicolon and filter empty
                constants = [c.strip() for c in define_const.text.split(';') if c.strip()]
                project_metadata['define_constants'].extend(constants)
            
            # LangVersion (Phase 2.2)
            lang_ver = prop_group.find('LangVersion')
            if lang_ver is not None and lang_ver.text:
                project_metadata['lang_version'] = lang_ver.text
            
            # Nullable (Phase 2.2)
            nullable = prop_group.find('Nullable')
            if nullable is not None and nullable.text:
                project_metadata['nullable'] = nullable.text
        
        # Infer OutputType if missing, based on Sdk attribute
        if not project_metadata['output_type']:
            sdk = root.get('Sdk')
            if sdk:
                if sdk.startswith("Microsoft.NET.Sdk.Web"):
                    project_metadata['output_type'] = "Exe"
                elif sdk.startswith("Microsoft.NET.Sdk.Worker"):
                    project_metadata['output_type'] = "Exe"
                elif sdk.startswith("Microsoft.NET.Sdk"):
                    project_metadata['output_type'] = "Library"
        
        # Create a single symbol with all project metadata
        if any(project_metadata.values()):
            # Remove duplicates from define_constants
            project_metadata['define_constants'] = list(set(project_metadata['define_constants']))
            
            symbols.append(ParsedSymbol(
                kind=SymbolKindEnum.CLASS,  # Using CLASS to represent project
                name='ProjectMetadata',
                start_line=0,
                end_line=0,
                start_column=0,
                end_column=0,
                signature='Project Configuration',
                documentation='Project-level configuration and compilation settings',
                structured_docs={
                    'type': 'project_metadata',
                    **project_metadata
                }
            ))
        
        return symbols
