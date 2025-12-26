from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from pathlib import Path
from src.config.enums import LanguageEnum, SymbolKindEnum, AccessModifierEnum

@dataclass
class ParsedSymbol:
    """Represents a parsed code symbol."""
    kind: SymbolKindEnum
    name: str
    start_line: int
    end_line: int
    start_column: int
    end_column: int
    signature: Optional[str] = None
    documentation: Optional[str] = None
    structured_docs: Optional[Dict[str, Any]] = None  # XML/JSDoc structured documentation
    parameters: List[Dict[str, Any]] = None
    return_type: Optional[str] = None
    access_modifier: Optional[AccessModifierEnum] = None
    parent_name: Optional[str] = None
    fully_qualified_name: Optional[str] = None
    references: List[Dict[str, Any]] = None  # List of extracted references (name, location, type)
    generic_parameters: List[Dict[str, Any]] = None  # Phase 2.3
    constraints: List[Dict[str, Any]] = None  # Phase 2.3
    complexity: int = 1  # Phase 3: Cyclomatic complexity score
    
    def __post_init__(self):
        """Initialize mutable defaults."""
        if self.parameters is None:
            self.parameters = []
        if self.references is None:
            self.references = []
        if self.generic_parameters is None:
            self.generic_parameters = []
        if self.constraints is None:
            self.constraints = []

@dataclass
class ParseResult:
    """Result of parsing a file."""
    language: LanguageEnum
    file_path: str
    symbols: List[ParsedSymbol]
    imports: List[str]
    exports: List[str]
    parse_errors: List[str]
    parse_duration_ms: float
    api_calls: List[Dict[str, Any]] = None  # Phase 2: HTTP API calls detected
    events: List[Dict[str, Any]] = None  # Phase 2: Event publishing/subscription detected
    
    def __post_init__(self):
        """Initialize mutable defaults."""
        if self.symbols is None:
            self.symbols = []
        if self.imports is None:
            self.imports = []
        if self.exports is None:
            self.exports = []
        if self.parse_errors is None:
            self.parse_errors = []
        if self.api_calls is None:
            self.api_calls = []
        if self.events is None:
            self.events = []

class BaseParser(ABC):
    """Base parser interface for all language parsers."""
    
    @abstractmethod
    def parse(self, code: str, file_path: Optional[str] = None) -> ParseResult:
        """
        Parse source code and extract symbols.
        
        Args:
            code: Source code content
            file_path: Optional file path for context
            
        Returns:
            ParseResult with extracted symbols
        """
        pass
    
    @abstractmethod
    def get_language(self) -> LanguageEnum:
        """Return the language this parser handles."""
        pass
    
    @abstractmethod
    def is_supported(self, file_path: Path) -> bool:
        """Check if this parser supports the given file."""
        pass
    
    async def cleanup(self):
        """
        Clean up any resources (e.g., persistent processes).
        Override in subclasses if cleanup is needed.
        """
        pass

