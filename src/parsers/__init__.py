import threading
import asyncio
from typing import Dict, Type
from pathlib import Path
from src.config.enums import LanguageEnum
from src.parsers.base_parser import BaseParser, ParseResult, ParsedSymbol
from src.parsers.csharp_parser import CSharpParser
from src.parsers.hybrid_parser import HybridCSharpParser
from src.parsers.javascript_parser import JavaScriptParser, TypeScriptParser
from src.parsers.vue_parser import VueParser
from src.parsers.markdown_parser import MarkdownParser
from src.parsers.csproj_parser import CsProjParser
from src.parsers.solution_parser import SolutionParser
from src.parsers.package_json_parser import PackageJsonParser
from src.parsers.appsettings_parser import AppSettingsParser
from src.parsers.sql_parser import SQLParser
from src.parsers.openapi_parser import OpenAPIParser
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

class ParserFactory:
    """Factory for creating language-specific parsers."""
    
    _thread_local = threading.local()
    
    @classmethod
    def get_parser(cls, language: LanguageEnum) -> BaseParser:
        """
        Get parser for language.
        
        Args:
            language: Language enum
            
        Returns:
            Parser instance
        """
        if not hasattr(cls._thread_local, "parsers"):
            cls._thread_local.parsers = {}
            
        if language not in cls._thread_local.parsers:
            cls._thread_local.parsers[language] = cls._create_parser(language)
        
        return cls._thread_local.parsers[language]
    
    @classmethod
    def get_parser_for_file(cls, file_path: Path) -> BaseParser:
        """
        Get appropriate parser for file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Parser instance
        """
        suffix = file_path.suffix.lower()
        
        if suffix == '.cs':
            return cls.get_parser(LanguageEnum.CSHARP)
        elif suffix in ['.js', '.jsx', '.mjs']:
            return cls.get_parser(LanguageEnum.JAVASCRIPT)
        elif suffix == '.ts':
            return cls.get_parser(LanguageEnum.TYPESCRIPT)
        elif suffix == '.tsx':
            # TSX files need the JSX-aware grammar
            return TypeScriptParser(use_tsx=True)
        elif suffix == '.vue':
            return cls.get_parser(LanguageEnum.VUE)
        elif suffix in ['.md', '.markdown']:
            return cls.get_parser(LanguageEnum.MARKDOWN)
        elif suffix in ['.sql', '.ddl']:
            return cls.get_parser(LanguageEnum.SQL)
        elif suffix == '.csproj':
            return CsProjParser()
        elif suffix == '.sln':
            return SolutionParser()
        elif file_path.name.lower() == 'package.json':
            return PackageJsonParser()
        elif file_path.name.lower().startswith('appsettings') and suffix == '.json':
            return AppSettingsParser()
        elif file_path.name.lower() in ['openapi.json', 'openapi.yaml', 'openapi.yml', 
                                          'swagger.json', 'swagger.yaml', 'swagger.yml']:
            return OpenAPIParser()
        elif suffix == '.json':
            # Generic JSON files (e.g., global.json, tsconfig.json, launchSettings.json)
            # These don't contain code symbols, so we return an empty parser
            logger.debug("skipping_generic_json_file", file_path=str(file_path))
            from src.parsers.noop_parser import NoOpParser
            return NoOpParser()
        else:
            logger.warning("unsupported_file_type", file_path=str(file_path))
            raise ValueError(f"Unsupported file type: {suffix}")
    
    @classmethod
    def _create_parser(cls, language: LanguageEnum) -> BaseParser:
        """Create parser instance."""
        parser_map: Dict[LanguageEnum, Type[BaseParser]] = {
            LanguageEnum.CSHARP: HybridCSharpParser,
            LanguageEnum.JAVASCRIPT: JavaScriptParser,
            LanguageEnum.TYPESCRIPT: TypeScriptParser,
            LanguageEnum.VUE: VueParser,
            LanguageEnum.MARKDOWN: MarkdownParser,
            LanguageEnum.SQL: SQLParser,
        }
        
        parser_class = parser_map.get(language)
        if not parser_class:
            raise ValueError(f"No parser available for language: {language}")
        
        return parser_class()

    @classmethod
    async def cleanup(cls):
        """Clean up all cached parsers."""
        if hasattr(cls._thread_local, "parsers"):
            for parser in cls._thread_local.parsers.values():
                await parser.cleanup()
            cls._thread_local.parsers.clear()

# Convenience function
def parse_file(file_path: Path) -> ParseResult:
    """
    Parse a file and return symbols.
    
    Args:
        file_path: Path to file
        
    Returns:
        ParseResult
    """
    parser = ParserFactory.get_parser_for_file(file_path)
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        code = f.read()
    
    return parser.parse(code, str(file_path))

async def parse_file_async(file_path: Path) -> ParseResult:
    """
    Parse a file asynchronously.
    
    Optimized to run async-capable parsers (like C# Roslyn) on the current loop,
    avoiding the overhead and instability of spinning up new loops via asyncio.run().
    
    Args:
        file_path: Path to file
        
    Returns:
        ParseResult
    """
    parser = ParserFactory.get_parser_for_file(file_path)
    
    # If parser supports async natively (e.g. HybridCSharpParser), run on current loop
    if hasattr(parser, 'parse_async'):
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()
        return await parser.parse_async(code, str(file_path))
    
    # Otherwise offload sync parsing to thread to avoid blocking main loop
    return await asyncio.to_thread(parse_file, file_path)

# Export all public APIs
__all__ = [
    'BaseParser',
    'ParseResult',
    'ParsedSymbol',
    'CSharpParser',
    'HybridCSharpParser',
    'JavaScriptParser',
    'TypeScriptParser',
    'VueParser',
    'ParserFactory',
    'parse_file',
    'parse_file_async',
]
