"""Parser for .sln (Visual Studio Solution) files."""

import re
from typing import List, Optional, Dict, Any
from pathlib import Path
from src.config.enums import LanguageEnum, SymbolKindEnum
from src.parsers.base_parser import BaseParser, ParseResult, ParsedSymbol


class SolutionParser(BaseParser):
    """Parser for Visual Studio .sln solution files."""
    
    # Project type GUIDs (common ones)
    PROJECT_TYPE_GUIDS = {
        '{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}': 'C# Project',
        '{F184B08F-C81C-45F6-A57F-5ABD9991F28F}': 'VB.NET Project',
        '{8BC9CEB8-8B4A-11D0-8D11-00A0C91BC942}': 'C++ Project',
        '{E24C65DC-7377-472B-9ABA-BC803B73C61A}': 'Web Site Project',
        '{2150E333-8FDC-42A3-9474-1A3956D46DE8}': 'Solution Folder',
        '{9A19103F-16F7-4668-BE54-9A1E7A4F7556}': 'SDK-style C# Project',
    }
    
    def __init__(self):
        self.language = LanguageEnum.CSHARP
    
    def get_language(self) -> LanguageEnum:
        """Return the language this parser handles."""
        return self.language
    
    def is_supported(self, file_path: Path) -> bool:
        """Check if file is a .sln file."""
        return file_path.suffix.lower() == '.sln'
    
    def parse(self, code: str, file_path: Optional[str] = None) -> ParseResult:
        """
        Parse .sln file and extract:
        - Solution metadata (version, Visual Studio version)
        - Projects (name, path, GUID, type)
        - Solution configurations
        - Project configurations
        - Nested projects (solution folders)
        """
        import time
        start_time = time.time()
        
        symbols = []
        imports = []  # Store project paths as imports
        errors = []
        
        try:
            # Extract solution metadata
            solution_metadata = self._extract_solution_metadata(code, file_path)
            if solution_metadata:
                symbols.append(solution_metadata)
            
            # Extract projects
            projects = self._extract_projects(code, file_path)
            symbols.extend(projects)
            imports.extend([proj.structured_docs.get('project_path', '') for proj in projects if proj.structured_docs])
            
            # Extract solution configurations
            configs = self._extract_configurations(code, file_path)
            symbols.extend(configs)
            
            # Extract nested project structure (solution folders)
            nested_projects = self._extract_nested_projects(code, file_path)
            if nested_projects:
                # Store as structured data in solution metadata
                if solution_metadata and solution_metadata.structured_docs:
                    solution_metadata.structured_docs['nested_projects'] = nested_projects
            
        except Exception as e:
            errors.append(f"Solution parsing error: {str(e)}")
        
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
    
    def _extract_solution_metadata(self, code: str, file_path: Optional[str]) -> Optional[ParsedSymbol]:
        """Extract solution-level metadata."""
        # Extract format version
        format_version_match = re.search(r'Microsoft Visual Studio Solution File, Format Version ([\d.]+)', code)
        format_version = format_version_match.group(1) if format_version_match else 'Unknown'
        
        # Extract Visual Studio version
        vs_version_match = re.search(r'# Visual Studio Version ([\d]+)', code)
        vs_version = vs_version_match.group(1) if vs_version_match else None
        
        # Extract VisualStudioVersion
        vs_full_version_match = re.search(r'VisualStudioVersion = ([\d.]+)', code)
        vs_full_version = vs_full_version_match.group(1) if vs_full_version_match else None
        
        # Extract MinimumVisualStudioVersion
        min_vs_version_match = re.search(r'MinimumVisualStudioVersion = ([\d.]+)', code)
        min_vs_version = min_vs_version_match.group(1) if min_vs_version_match else None
        
        # Get solution name from file path
        solution_name = Path(file_path).stem if file_path else 'Unknown'
        
        return ParsedSymbol(
            kind=SymbolKindEnum.MODULE,  # Using MODULE to represent solution
            name=solution_name,
            start_line=0,
            end_line=0,
            start_column=0,
            end_column=0,
            signature=f"Solution: {solution_name}",
            documentation=f"Visual Studio Solution (Format {format_version})",
            structured_docs={
                'type': 'solution',
                'format_version': format_version,
                'visual_studio_version': vs_version,
                'visual_studio_full_version': vs_full_version,
                'minimum_visual_studio_version': min_vs_version,
                'solution_path': file_path
            }
        )
    
    def _extract_projects(self, code: str, file_path: Optional[str]) -> List[ParsedSymbol]:
        """Extract project entries from solution."""
        symbols = []
        
        # Pattern: Project("{TYPE-GUID}") = "ProjectName", "ProjectPath", "{PROJECT-GUID}"
        project_pattern = re.compile(
            r'Project\("(\{[A-F0-9-]+\})"\)\s*=\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*"(\{[A-F0-9-]+\})"',
            re.IGNORECASE
        )
        
        for match in project_pattern.finditer(code):
            type_guid = match.group(1).upper()
            project_name = match.group(2)
            project_path = match.group(3)
            project_guid = match.group(4).upper()
            
            # Determine project type
            project_type = self.PROJECT_TYPE_GUIDS.get(type_guid, 'Unknown Project Type')
            
            # Skip solution folders for now (they're handled separately)
            if type_guid == '{2150E333-8FDC-42A3-9474-1A3956D46DE8}':
                continue
            
            symbols.append(ParsedSymbol(
                kind=SymbolKindEnum.CLASS,  # Using CLASS to represent projects
                name=project_name,
                start_line=0,
                end_line=0,
                start_column=0,
                end_column=0,
                signature=f"Project: {project_name}",
                documentation=f"{project_type} at {project_path}",
                structured_docs={
                    'type': 'project',
                    'project_name': project_name,
                    'project_path': project_path,
                    'project_guid': project_guid,
                    'project_type_guid': type_guid,
                    'project_type': project_type
                }
            ))
        
        return symbols
    
    def _extract_configurations(self, code: str, file_path: Optional[str]) -> List[ParsedSymbol]:
        """Extract solution configurations."""
        symbols = []
        
        # Find GlobalSection(SolutionConfigurationPlatforms)
        config_section_match = re.search(
            r'GlobalSection\(SolutionConfigurationPlatforms\)\s*=\s*preSolution(.*?)EndGlobalSection',
            code,
            re.DOTALL
        )
        
        if config_section_match:
            config_content = config_section_match.group(1)
            
            # Pattern: Debug|Any CPU = Debug|Any CPU
            config_pattern = re.compile(r'([^=]+)\s*=\s*([^\n]+)')
            
            configurations = []
            for match in config_pattern.finditer(config_content):
                config_name = match.group(1).strip()
                if config_name:
                    configurations.append(config_name)
            
            if configurations:
                symbols.append(ParsedSymbol(
                    kind=SymbolKindEnum.PROPERTY,
                    name='SolutionConfigurations',
                    start_line=0,
                    end_line=0,
                    start_column=0,
                    end_column=0,
                    signature=f"Solution Configurations: {len(configurations)} configurations",
                    documentation=f"Available build configurations: {', '.join(configurations[:3])}{'...' if len(configurations) > 3 else ''}",
                    structured_docs={
                        'type': 'solution_configurations',
                        'configurations': configurations
                    }
                ))
        
        return symbols
    
    def _extract_nested_projects(self, code: str, file_path: Optional[str]) -> Dict[str, str]:
        """Extract nested project structure (solution folders)."""
        nested_projects = {}
        
        # Find GlobalSection(NestedProjects)
        nested_section_match = re.search(
            r'GlobalSection\(NestedProjects\)\s*=\s*preSolution(.*?)EndGlobalSection',
            code,
            re.DOTALL
        )
        
        if nested_section_match:
            nested_content = nested_section_match.group(1)
            
            # Pattern: {CHILD-GUID} = {PARENT-GUID}
            nested_pattern = re.compile(r'(\{[A-F0-9-]+\})\s*=\s*(\{[A-F0-9-]+\})', re.IGNORECASE)
            
            for match in nested_pattern.finditer(nested_content):
                child_guid = match.group(1).upper()
                parent_guid = match.group(2).upper()
                nested_projects[child_guid] = parent_guid
        
        return nested_projects
