import tree_sitter
from tree_sitter import Language, Parser
from typing import Optional, List, Dict, Any
from pathlib import Path
import time
from contextlib import contextmanager
from src.config.enums import LanguageEnum, SymbolKindEnum, AccessModifierEnum
from src.parsers.base_parser import BaseParser, ParseResult, ParsedSymbol
from src.utils.logging_config import get_logger
from src.utils.metrics import parsing_duration, files_parsed_total, parsing_errors_total

logger = get_logger(__name__)

class TimeoutError(Exception):
    """Raised when parsing exceeds time limit."""
    pass

@contextmanager
def timeout(seconds: int):
    """
    Context manager for timing out operations.
    
    Note: This uses time tracking rather than signals to be compatible with
    Celery worker processes (signals only work in main thread).
    This will raise an error after timeout, but cannot interrupt blocking operations.
    """
    start_time = time.time()
    
    try:
        yield
        elapsed = time.time() - start_time
        if elapsed > seconds:
            raise TimeoutError(f"Operation exceeded time limit of {seconds} seconds (took {elapsed:.2f}s)")
    except TimeoutError:
        raise

class TreeSitterParser(BaseParser):
    """Base Tree-sitter parser with common functionality."""
    
    def __init__(self, language: LanguageEnum, language_module):
        """
        Initialize Tree-sitter parser.
        
        Args:
            language: Language enum
            language_module: The tree-sitter language module (e.g., tree_sitter_c_sharp)
        """
        self.language = language
        try:
            language_capsule = language_module.language()
            self.ts_language = Language(language_capsule)
            self.parser = Parser(self.ts_language)
            logger.info("tree_sitter_parser_initialized", language=language.value)
        except Exception as e:
            logger.error("tree_sitter_parser_init_failed", language=language.value, error=str(e))
            raise
    
    def parse(self, code: str, file_path: Optional[str] = None) -> ParseResult:
        """Parse code with timeout protection."""
        start_time = time.time()
        symbols = []
        imports = []
        exports = []
        api_calls = []
        errors = []
        
        try:
            with timeout(60):  # 60 second timeout
                tree = self.parser.parse(bytes(code, "utf8"))
                
                if tree.root_node.has_error:
                    errors.append("Syntax errors detected in code")
                
                # Extract symbols using language-specific logic
                symbols = self._extract_symbols(tree.root_node, code)
                imports = self._extract_imports(tree.root_node, code)
                exports = self._extract_exports(tree.root_node, code)
                
                # Extract API calls if supported (JavaScript/TypeScript parsers)
                if hasattr(self, 'api_calls'):
                    api_calls = self.api_calls
                
        except TimeoutError as e:
            logger.error("parsing_timeout", file_path=file_path, error=str(e))
            errors.append(str(e))
        except Exception as e:
            logger.error("parsing_failed", file_path=file_path, error=str(e))
            errors.append(f"Parsing error: {str(e)}")
        
        duration_ms = (time.time() - start_time) * 1000
        
        # Record metrics
        parsing_duration.labels(language=self.language.value).observe(duration_ms / 1000)
        
        # Track success/failure
        status = "error" if errors else "success"
        files_parsed_total.labels(language=self.language.value, status=status).inc()
        
        # Track individual errors
        if errors:
            for error in errors:
                error_type = "timeout" if "timeout" in error.lower() else "syntax_error"
                parsing_errors_total.labels(language=self.language.value, error_type=error_type).inc()
        
        return ParseResult(
            language=self.language,
            file_path=file_path or "unknown",
            symbols=symbols,
            imports=imports,
            exports=exports,
            parse_errors=errors,
            parse_duration_ms=duration_ms,
            api_calls=api_calls,
            events=getattr(self, 'events', []) # Extract events if supported
        )
    
    def get_language(self) -> LanguageEnum:
        """Return the language this parser handles."""
        return self.language
    
    def _extract_symbols(self, node: tree_sitter.Node, code: str) -> List[ParsedSymbol]:
        """Extract symbols from AST. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement _extract_symbols")
    
    def _extract_imports(self, node: tree_sitter.Node, code: str) -> List[str]:
        """Extract import statements. Override in subclasses."""
        return []
    
    def _extract_exports(self, node: tree_sitter.Node, code: str) -> List[str]:
        """Extract export statements. Override in subclasses."""
        return []
    
    def _get_node_text(self, node: Optional[tree_sitter.Node], code: str) -> str:
        """Get text content of a node."""
        if not node:
            return ""
        # Tree-sitter uses byte offsets, not character offsets
        # We need to encode the string to bytes first, slice, then decode
        code_bytes = code.encode('utf-8')
        node_bytes = code_bytes[node.start_byte:node.end_byte]
        return node_bytes.decode('utf-8')
    
    def _find_documentation(self, node: tree_sitter.Node, code: str) -> Optional[str]:
        """Find documentation comment above a node."""
        # Look for comment nodes before this node
        if node.prev_sibling and node.prev_sibling.type in ['comment', 'block_comment', 'line_comment']:
            doc = self._get_node_text(node.prev_sibling, code).strip('/*/ \t\n')
            return doc if doc else None
        return None
    
    def _find_child_by_type(self, node: tree_sitter.Node, node_type: str) -> Optional[tree_sitter.Node]:
        """Find first child node of given type."""
        for child in node.children:
            if child.type == node_type:
                return child
        return None

