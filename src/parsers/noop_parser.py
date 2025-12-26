"""
No-op parser for files that don't need parsing (e.g., generic JSON config files).
"""
import time
from pathlib import Path
from src.parsers.base_parser import BaseParser, ParseResult
from src.config.enums import LanguageEnum


class NoOpParser(BaseParser):
    """Parser that returns empty results for files that don't contain code symbols."""
    
    def parse(self, code: str, file_path: str = None) -> ParseResult:
        """Return empty parse result."""
        start_time = time.time()
        
        result = ParseResult(
            language=LanguageEnum.UNKNOWN,
            file_path=file_path or "",
            symbols=[],
            imports=[],
            exports=[],
            parse_errors=[],
            parse_duration_ms=(time.time() - start_time) * 1000,
            api_calls=[],
            events=[]
        )
        
        return result
    
    def get_language(self) -> LanguageEnum:
        """Return unknown language."""
        return LanguageEnum.UNKNOWN
    
    def is_supported(self, file_path: Path) -> bool:
        """All files are 'supported' by returning empty results."""
        return True
