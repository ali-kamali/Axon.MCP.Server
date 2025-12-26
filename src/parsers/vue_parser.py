import re
from typing import List, Optional
from pathlib import Path
from src.config.enums import LanguageEnum, SymbolKindEnum
from src.parsers.base_parser import BaseParser, ParseResult, ParsedSymbol
from src.parsers.react_analyzer import VueAnalyzer
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

class VueParser(BaseParser):
    """Vue.js Single File Component parser."""
    
    def __init__(self):
        # Lazy import to avoid circular dependency
        from src.parsers.javascript_parser import JavaScriptParser, TypeScriptParser
        self.js_parser = JavaScriptParser()
        self.ts_parser = TypeScriptParser(use_tsx=False)
        self.vue_analyzer = VueAnalyzer()
    
    def get_language(self) -> LanguageEnum:
        """Return Vue language."""
        return LanguageEnum.VUE
    
    def is_supported(self, file_path: Path) -> bool:
        """Check if file is a Vue file."""
        return file_path.suffix.lower() == '.vue'
    
    def parse(self, code: str, file_path: Optional[str] = None) -> ParseResult:
        """Parse Vue SFC and extract script section."""
        # Extract script section with line offset
        script_content, script_lang, line_offset = self._extract_script_section(code)
        
        if not script_content:
            logger.warning("no_script_section_found", file_path=file_path)
            return ParseResult(
                language=LanguageEnum.VUE,
                file_path=file_path or "unknown",
                symbols=[],
                imports=[],
                exports=[],
                parse_errors=["No script section found"],
                parse_duration_ms=0
            )
        
        # Parse script section with appropriate parser
        if script_lang == 'ts' or script_lang == 'tsx':
            # Use TSX parser if script contains JSX
            has_jsx = '<' in script_content and '>' in script_content and any(
                tag in script_content for tag in ['<div', '<span', '<component', '<template']
            )
            if has_jsx or script_lang == 'tsx':
                # Create TSX-aware parser for JSX support
                from src.parsers.javascript_parser import TypeScriptParser
                tsx_parser = TypeScriptParser(use_tsx=True)
                result = tsx_parser.parse(script_content, file_path)
            else:
                result = self.ts_parser.parse(script_content, file_path)
        else:
            result = self.js_parser.parse(script_content, file_path)
        
        # Update language to Vue
        result.language = LanguageEnum.VUE
        
        # Adjust symbol line numbers to account for Vue file structure
        for symbol in result.symbols:
            symbol.start_line += line_offset
            symbol.end_line += line_offset
        
        # Extract template and style information
        template_content = self._extract_template_section(code)
        has_style = self._has_section(code, 'style')
        
        # Analyze Vue component
        if result.symbols and template_content:
            # Find the main component/export
            main_component = next((s for s in result.symbols if s.kind in [SymbolKindEnum.CLASS, SymbolKindEnum.FUNCTION]), None)
            
            if main_component:
                vue_metadata = self.vue_analyzer.analyze_vue_component(
                    {
                        'name': main_component.name,
                        'signature': main_component.signature,
                        'parameters': main_component.parameters
                    },
                    template_content,
                    script_content
                )
                
                # Add Vue metadata to component's structured_docs
                if not main_component.structured_docs:
                    main_component.structured_docs = {}
                
                main_component.structured_docs['vue_component'] = {
                    'props': vue_metadata['props'],
                    'emits': vue_metadata['emits'],
                    'composables': vue_metadata['composables'],
                    'template_components': vue_metadata['template_components'],
                    'is_composition_api': vue_metadata['is_composition_api']
                }
        
        logger.info(
            "vue_file_parsed",
            file_path=file_path,
            script_lang=script_lang,
            has_template=template_content is not None,
            has_style=has_style,
            symbol_count=len(result.symbols)
        )
        
        return result
    
    def _extract_script_section(self, code: str) -> tuple:
        """
        Extract script content from Vue SFC.
        
        Returns:
            Tuple of (script_content, language, line_offset) where language is 'js' or 'ts'
            and line_offset is the line number where the script content starts
        """
        # Match <script> or <script lang="ts"> or <script setup lang="ts">
        script_pattern = r'<script(?:\s+(?:setup\s+)?lang=["\'](\w+)["\']|\s+setup)?[^>]*>(.*?)</script>'
        match = re.search(script_pattern, code, re.DOTALL | re.IGNORECASE)
        
        if match:
            lang = match.group(1) or 'js'
            content = match.group(2)
            
            # Calculate line offset - count newlines before the script content
            script_start_pos = match.start(2)  # Position where script content starts
            line_offset = code[:script_start_pos].count('\n')
            
            return content.strip(), lang, line_offset
        
        return None, 'js', 0
    
    def _has_section(self, code: str, section: str) -> bool:
        """Check if SFC has a specific section."""
        pattern = f'<{section}[^>]*>'
        return bool(re.search(pattern, code, re.IGNORECASE))
    
    def _extract_template_section(self, code: str) -> Optional[str]:
        """
        Extract template content from Vue SFC.
        
        Returns:
            Template content or None if not found
        """
        template_pattern = r'<template[^>]*>(.*?)</template>'
        match = re.search(template_pattern, code, re.DOTALL | re.IGNORECASE)
        
        if match:
            return match.group(1).strip()
        
        return None

