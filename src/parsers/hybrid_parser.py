"""
Hybrid C# Parser - Combines Tree-sitter and Roslyn

Runs both parsers in parallel and merges results:
- Tree-sitter: Fast structure extraction (classes, methods, properties)
- Roslyn: Accurate semantic analysis (types, inheritance, interfaces)
"""
import asyncio
from typing import List, Dict, Optional, Any
from pathlib import Path

from src.parsers.csharp_parser import CSharpParser
from src.parsers.roslyn_integration import RoslynAnalyzer, RoslynResult
from src.parsers.base_parser import ParseResult, ParsedSymbol
from src.config.enums import LanguageEnum
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class HybridCSharpParser:
    """
    Hybrid C# parser combining Tree-sitter and Roslyn.
    
    Strategy:
    1. Run both parsers in parallel
    2. Use Tree-sitter as base (fast, complete structure)
    3. Enrich with Roslyn semantic data (types, inheritance)
    4. Graceful fallback to Tree-sitter if Roslyn fails
    """
    
    def __init__(self):
        """Initialize hybrid parser with both backends."""
        self.tree_sitter = CSharpParser()
        self.roslyn = RoslynAnalyzer()
        self.use_roslyn = self.roslyn.is_available()
        
        if self.use_roslyn:
            logger.info("hybrid_parser_initialized", mode="hybrid")
        else:
            logger.info("hybrid_parser_initialized", mode="tree_sitter_only")
    
    def parse(self, code: str, file_path: str) -> ParseResult:
        """
        Parse C# code using hybrid approach.
        
        This is a synchronous wrapper for async parsing.
        For async contexts, use parse_async() directly.
        
        Args:
            code: C# source code
            file_path: Path to the file
            
        Returns:
            ParseResult with merged symbols
        """
        try:
            # Check if there's already a running loop
            loop = asyncio.get_running_loop()
            if loop.is_running():
                # We are in an async context. We cannot mistakenly use asyncio.run().
                # Since strict return type is ParseResult (sync), we can't return a coroutine.
                # However, usually this method is called from a thread executor (via to_thread),
                # where no loop is running. 
                # If we hit this, it's a bug in the caller.
                logger.error("sync_parse_called_from_async_loop", file_path=file_path)
                raise RuntimeError("Cannot call synchronous parse() from an active event loop. Use parse_async() instead.")
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            pass
            
        return asyncio.run(self.parse_async(code, file_path))
    
    async def parse_async(self, code: str, file_path: str) -> ParseResult:
        """
        Parse C# code asynchronously using hybrid approach.
        
        Args:
            code: C# source code
            file_path: Path to the file
            
        Returns:
            ParseResult with merged symbols
        """
        if not self.use_roslyn:
            # Roslyn not available, use Tree-sitter only
            return self.tree_sitter.parse(code, file_path)
        
        try:
            # Run both parsers in parallel
            ts_result, roslyn_result = await asyncio.gather(
                self._parse_with_tree_sitter(code, file_path),
                self._parse_with_roslyn(code, file_path),
                return_exceptions=True
            )
            
            # Check for exceptions
            if isinstance(ts_result, Exception):
                logger.error("tree_sitter_parse_failed", error=str(ts_result))
                ts_result = None
            
            if isinstance(roslyn_result, Exception):
                logger.warning("roslyn_parse_failed", error=str(roslyn_result))
                roslyn_result = None
            
            # Merge results
            if ts_result and roslyn_result and roslyn_result.success:
                return self._merge_results(ts_result, roslyn_result, file_path)
            elif ts_result:
                # Roslyn failed, use Tree-sitter only
                logger.info("using_tree_sitter_only", file_path=file_path)
                return ts_result
            else:
                # Both failed, return empty result
                logger.error("both_parsers_failed", file_path=file_path)
                return ParseResult(
                    file_path=file_path,
                    language=LanguageEnum.CSHARP,
                    symbols=[],
                    imports=[],
                    errors=["Both parsers failed"]
                )
                
        except Exception as e:
            logger.error("hybrid_parse_failed", file_path=file_path, error=str(e))
            # Fallback to Tree-sitter
            return self.tree_sitter.parse(code, file_path)
    
    async def _parse_with_tree_sitter(self, code: str, file_path: str) -> ParseResult:
        """Parse with Tree-sitter (sync parser, run in executor)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.tree_sitter.parse,
            code,
            file_path
        )
    
    async def _parse_with_roslyn(self, code: str, file_path: str) -> RoslynResult:
        """Parse with Roslyn (already async)."""
        return await self.roslyn.analyze_file(code, file_path)
    
    def _merge_results(
        self,
        ts_result: ParseResult,
        roslyn_result: RoslynResult,
        file_path: str
    ) -> ParseResult:
        """
        Merge Tree-sitter and Roslyn results.
        
        Strategy:
        1. Use Tree-sitter symbols as base (complete structure)
        2. Match with Roslyn symbols by name and kind
        3. Enrich Tree-sitter symbols with Roslyn semantic data
        4. Keep unmatched Tree-sitter symbols (Roslyn might miss some)
        
        Args:
            ts_result: Tree-sitter parse result
            roslyn_result: Roslyn analysis result
            file_path: File path for logging
            
        Returns:
            ParseResult with enriched symbols
        """
        enriched_symbols = []
        
        # Create lookup map for Roslyn symbols
        roslyn_map = {
            self._get_symbol_key(rs): rs
            for rs in roslyn_result.symbols
        }
        
        # Enrich Tree-sitter symbols with Roslyn data
        for ts_symbol in ts_result.symbols:
            key = self._get_symbol_key_from_parsed(ts_symbol)
            roslyn_symbol = roslyn_map.get(key)
            
            if roslyn_symbol:
                # Match found - enrich with Roslyn data
                enriched = self._enrich_symbol(ts_symbol, roslyn_symbol)
                enriched_symbols.append(enriched)
            else:
                # No match - keep Tree-sitter symbol as-is
                enriched_symbols.append(ts_symbol)
        
        logger.info(
            "symbols_merged",
            file_path=file_path,
            tree_sitter_count=len(ts_result.symbols),
            roslyn_count=len(roslyn_result.symbols),
            enriched_count=len(enriched_symbols)
        )
        
        return ParseResult(
            file_path=file_path,
            language=LanguageEnum.CSHARP,
            symbols=enriched_symbols,
            imports=getattr(ts_result, 'imports', []),
            exports=getattr(ts_result, 'exports', []),
            parse_errors=getattr(ts_result, 'parse_errors', []),
            parse_duration_ms=getattr(ts_result, 'parse_duration_ms', 0.0)
        )
    
    def _get_symbol_key(self, roslyn_symbol) -> str:
        """Generate unique key for Roslyn symbol."""
        # Use name + kind for matching
        return f"{roslyn_symbol.name}:{roslyn_symbol.kind}"
    
    def _get_symbol_key_from_parsed(self, parsed_symbol: ParsedSymbol) -> str:
        """Generate unique key for ParsedSymbol."""
        # Map SymbolKindEnum to Roslyn kind strings
        kind_map = {
            "CLASS": "NamedType",
            "INTERFACE": "NamedType",
            "METHOD": "Method",
            "PROPERTY": "Property",
            "FIELD": "Field",
            "CONSTRUCTOR": "Method"
        }
        roslyn_kind = kind_map.get(parsed_symbol.kind.name, parsed_symbol.kind.name)
        return f"{parsed_symbol.name}:{roslyn_kind}"
    
    def _enrich_symbol(self, ts_symbol: ParsedSymbol, roslyn_symbol) -> ParsedSymbol:
        """
        Enrich Tree-sitter symbol with Roslyn semantic data.
        
        Keep:
        - Tree-sitter: Structure (lines, columns, signature, documentation)
        - Roslyn: Semantics (FQN, types, inheritance, interfaces)
        
        Args:
            ts_symbol: Tree-sitter parsed symbol
            roslyn_symbol: Roslyn symbol with semantic data
            
        Returns:
            Enriched ParsedSymbol
        """
        # Start with Tree-sitter symbol
        enriched_dict = {
            'kind': ts_symbol.kind,
            'name': ts_symbol.name,
            'access_modifier': ts_symbol.access_modifier,
            'start_line': ts_symbol.start_line,
            'end_line': ts_symbol.end_line,
            'start_column': ts_symbol.start_column,
            'end_column': ts_symbol.end_column,
            'signature': ts_symbol.signature,
            'documentation': ts_symbol.documentation,
            'parameters': ts_symbol.parameters,
            'references': ts_symbol.references,
            'parent_name': ts_symbol.parent_name,
        }
        
        # Enrich with Roslyn semantic data
        enriched_dict['fully_qualified_name'] = roslyn_symbol.fully_qualified_name
        
        if roslyn_symbol.return_type:
            enriched_dict['return_type'] = roslyn_symbol.return_type
        
        # Merge structured_docs (ensure it's never None)
        structured_docs = ts_symbol.structured_docs.copy() if ts_symbol.structured_docs else {}
        
        # Add Roslyn metadata
        roslyn_metadata = {
            'roslyn_analyzed': True,
            'is_static': roslyn_symbol.is_static,
            'is_abstract': roslyn_symbol.is_abstract,
            'is_virtual': roslyn_symbol.is_virtual,
            'is_override': roslyn_symbol.is_override,
        }
        
        if roslyn_symbol.base_type:
            roslyn_metadata['base_type'] = roslyn_symbol.base_type
        
        if roslyn_symbol.interfaces:
            roslyn_metadata['interfaces'] = roslyn_symbol.interfaces
        
        if roslyn_symbol.generic_parameters:
            # Handle both object attributes and dictionaries
            roslyn_metadata['generic_parameters'] = []
            for gp in roslyn_symbol.generic_parameters:
                if isinstance(gp, dict):
                    # Already a dictionary
                    roslyn_metadata['generic_parameters'].append({
                        'name': gp.get('name', ''),
                        'constraints': gp.get('constraints', [])
                    })
                else:
                    # Object with attributes
                    roslyn_metadata['generic_parameters'].append({
                        'name': getattr(gp, 'name', ''),
                        'constraints': getattr(gp, 'constraints', [])
                    })
        
        structured_docs['roslyn'] = roslyn_metadata
        enriched_dict['structured_docs'] = structured_docs
        
        return ParsedSymbol(**enriched_dict)
    
    def get_parser_info(self) -> Dict[str, Any]:
        """Get information about the hybrid parser configuration."""
        return {
            'mode': 'hybrid' if self.use_roslyn else 'tree_sitter_only',
            'tree_sitter_available': True,
            'roslyn_available': self.use_roslyn,
            'roslyn_path': str(self.roslyn.analyzer_path) if self.use_roslyn else None
        }
        
    async def cleanup(self):
        """Clean up Roslyn analyzer process."""
        try:
            if self.use_roslyn and self.roslyn:
                await self.roslyn.stop()
        except Exception as e:
            logger.warning("roslyn_cleanup_failed", error=str(e))
