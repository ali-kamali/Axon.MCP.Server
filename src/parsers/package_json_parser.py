"""Parser for package.json files."""

import json
from typing import List, Optional
from pathlib import Path
from src.config.enums import LanguageEnum, SymbolKindEnum
from src.parsers.base_parser import BaseParser, ParseResult, ParsedSymbol


class PackageJsonParser(BaseParser):
    """Parser for package.json files."""
    
    def __init__(self):
        self.language = LanguageEnum.JAVASCRIPT
    
    def get_language(self) -> LanguageEnum:
        """Return the language this parser handles."""
        return self.language
    
    def is_supported(self, file_path: Path) -> bool:
        """Check if file is package.json."""
        return file_path.name.lower() == 'package.json'
    
    def parse(self, code: str, file_path: Optional[str] = None) -> ParseResult:
        """
        Parse package.json and extract:
        - Dependencies (production)
        - DevDependencies (development)
        - Scripts
        - Project metadata
        """
        import time
        start_time = time.time()
        
        symbols = []
        errors = []
        
        try:
            # Parse JSON
            data = json.loads(code)
            
            # Extract project metadata
            symbols.extend(self._extract_metadata(data, file_path))
            
            # Extract dependencies
            symbols.extend(self._extract_dependencies(
                data.get('dependencies', {}),
                is_dev=False,
                file_path=file_path
            ))
            
            # Extract devDependencies
            symbols.extend(self._extract_dependencies(
                data.get('devDependencies', {}),
                is_dev=True,
                file_path=file_path
            ))
            
            # Extract scripts
            symbols.extend(self._extract_scripts(data.get('scripts', {}), file_path))
            
        except json.JSONDecodeError as e:
            errors.append(f"JSON parsing error: {str(e)}")
        except Exception as e:
            errors.append(f"Package.json parsing error: {str(e)}")
        
        duration_ms = (time.time() - start_time) * 1000
        
        return ParseResult(
            language=self.language,
            file_path=file_path or "unknown",
            symbols=symbols,
            imports=[],
            exports=[],
            parse_errors=errors,
            parse_duration_ms=duration_ms
        )
    
    def _extract_metadata(self, data: dict, file_path: Optional[str]) -> List[ParsedSymbol]:
        """Extract project metadata."""
        symbols = []
        
        # Project name
        if 'name' in data:
            symbols.append(ParsedSymbol(
                kind=SymbolKindEnum.PROPERTY,
                name='name',
                start_line=0,
                end_line=0,
                start_column=0,
                end_column=0,
                signature=f"name: {data['name']}",
                documentation=f"Project name: {data['name']}",
                structured_docs={
                    'type': 'project_metadata',
                    'value': data['name']
                }
            ))
        
        # Version
        if 'version' in data:
            symbols.append(ParsedSymbol(
                kind=SymbolKindEnum.PROPERTY,
                name='version',
                start_line=0,
                end_line=0,
                start_column=0,
                end_column=0,
                signature=f"version: {data['version']}",
                documentation=f"Project version: {data['version']}",
                structured_docs={
                    'type': 'project_metadata',
                    'value': data['version']
                }
            ))
        
        # Description
        if 'description' in data:
            symbols.append(ParsedSymbol(
                kind=SymbolKindEnum.PROPERTY,
                name='description',
                start_line=0,
                end_line=0,
                start_column=0,
                end_column=0,
                signature=f"description: {data['description']}",
                documentation=data['description'],
                structured_docs={
                    'type': 'project_metadata',
                    'value': data['description']
                }
            ))
        
        return symbols
    
    def _extract_dependencies(
        self,
        deps: dict,
        is_dev: bool,
        file_path: Optional[str]
    ) -> List[ParsedSymbol]:
        """Extract dependencies."""
        symbols = []
        
        for name, version in deps.items():
            symbols.append(ParsedSymbol(
                kind=SymbolKindEnum.CONSTANT,  # Using CONSTANT for packages
                name=name,
                start_line=0,
                end_line=0,
                start_column=0,
                end_column=0,
                signature=f"{'devDependency' if is_dev else 'dependency'}: {name}@{version}",
                documentation=f"NPM package dependency{' (dev)' if is_dev else ''}",
                structured_docs={
                    'type': 'npm_package',
                    'version': version,
                    'is_dev_dependency': is_dev
                }
            ))
        
        return symbols
    
    def _extract_scripts(self, scripts: dict, file_path: Optional[str]) -> List[ParsedSymbol]:
        """Extract npm scripts."""
        symbols = []
        
        for name, command in scripts.items():
            symbols.append(ParsedSymbol(
                kind=SymbolKindEnum.FUNCTION,  # Using FUNCTION for scripts
                name=name,
                start_line=0,
                end_line=0,
                start_column=0,
                end_column=0,
                signature=f"script: npm run {name}",
                documentation=f"Script command: {command}",
                structured_docs={
                    'type': 'npm_script',
                    'command': command
                }
            ))
        
        return symbols

