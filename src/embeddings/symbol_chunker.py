"""Symbol-based chunking strategy."""

from typing import List, Optional
from dataclasses import dataclass

from src.database.models import Symbol, File, Chunk
from src.embeddings.chunk_context import ChunkContext, ChunkContextBuilder
from src.config.enums import SymbolKindEnum


@dataclass
class ChunkConfig:
    """Configuration for chunk creation."""
    
    max_token_size: int = 8000  # Modern embedding models support 8K+ tokens
    context_lines_before: int = 5  # Lines of context before symbol
    context_lines_after: int = 5  # Lines of context after symbol
    include_parent_context: bool = True
    include_imports: bool = True
    include_relationships: bool = True
    separate_docs_chunks: bool = True  # Create separate chunk for documentation


class SymbolChunker:
    """
    Symbol-based chunker that creates context-rich chunks.
    
    This replaces the old word-based chunking with semantic symbol-level chunking.
    """
    
    def __init__(self, config: Optional[ChunkConfig] = None):
        """
        Initialize symbol chunker.
        
        Args:
            config: Chunking configuration
        """
        self.config = config or ChunkConfig()
    
    def create_chunks_for_symbol(
        self,
        symbol: Symbol,
        file: File,
        context: ChunkContext,
        file_content: Optional[str] = None
    ) -> List[dict]:
        """
        Create rich chunks for a symbol.
        
        Args:
            symbol: Symbol to chunk
            file: File containing symbol
            context: Rich context for the symbol
            file_content: Optional full file content for extracting code
            
        Returns:
            List of chunk dictionaries ready for database insertion
        """
        chunks = []
        
        # Chunk 1: Code implementation chunk
        code_chunk = self._create_code_chunk(symbol, file, context, file_content)
        chunks.append(code_chunk)
        
        # Chunk 2: Documentation chunk (if significant documentation exists)
        if self.config.separate_docs_chunks and symbol.documentation:
            doc_chunk = self._create_documentation_chunk(symbol, file, context)
            chunks.append(doc_chunk)
        
        return chunks
    
    def _create_code_chunk(
        self,
        symbol: Symbol,
        file: File,
        context: ChunkContext,
        file_content: Optional[str]
    ) -> dict:
        """Create code-focused chunk."""
        parts = []
        
        # File header
        parts.append(f"File: {context.file_path}")
        
        # Namespace
        if context.namespace:
            parts.append(f"Namespace: {context.namespace}")
        
        # Imports (top 5 most relevant)
        if self.config.include_imports and context.imports:
            imports_str = ', '.join(context.imports[:5])
            parts.append(f"Imports: {imports_str}")
            if len(context.imports) > 5:
                parts.append(f"... and {len(context.imports) - 5} more")
        
        parts.append("")  # Blank line
        
        # Parent class context
        if self.config.include_parent_context and context.parent_class:
            parent = context.parent_class
            parts.append(f"// In class: {parent['name']}")
            parts.append(f"// {parent['signature']}")
            parts.append("")
        
        # Symbol signature
        if symbol.signature:
            parts.append(symbol.signature)
        
        # Symbol body (if available from file content)
        if file_content and symbol.start_line and symbol.end_line:
            body_lines = self._extract_symbol_body(
                file_content,
                symbol.start_line,
                symbol.end_line
            )
            if body_lines:
                parts.append(body_lines)
        
        # Relationships
        if self.config.include_relationships:
            if context.calls:
                calls_str = ', '.join(context.calls[:5])
                parts.append(f"\n// Calls: {calls_str}")
            if context.implements:
                impl_str = ', '.join(context.implements)
                parts.append(f"// Implements: {impl_str}")
            if context.inherits_from:
                inherit_str = ', '.join(context.inherits_from)
                parts.append(f"// Inherits from: {inherit_str}")
        
        content = '\n'.join(parts)
        
        # Build context metadata
        metadata = {
            'namespace': context.namespace,
            'imports': context.imports[:10],  # Store top 10 imports
            'parent_class': context.parent_class.get('name') if context.parent_class else None,
            'calls': context.calls[:10],
            'implements': context.implements,
            'inherits_from': context.inherits_from,
            'is_test': context.is_test,
            'is_public': context.is_public,
            'complexity': context.complexity
        }
        
        return {
            'content': content,
            'content_type': 'code',
            'chunk_subtype': 'implementation',
            'context_metadata': metadata,
            'start_line': symbol.start_line,
            'end_line': symbol.end_line
        }
    
    def _create_documentation_chunk(
        self,
        symbol: Symbol,
        file: File,
        context: ChunkContext
    ) -> dict:
        """Create documentation-focused chunk."""
        parts = []
        
        # Symbol name and kind
        parts.append(f"{symbol.name} ({symbol.kind.value})")
        parts.append(f"File: {context.file_path}")
        
        if context.namespace:
            parts.append(f"Namespace: {context.namespace}")
        
        parts.append("")  # Blank line
        
        # Documentation
        if symbol.documentation:
            parts.append(symbol.documentation)
        
        # Structured documentation (if available)
        if symbol.structured_docs:
            parts.append("\n--- Structured Documentation ---")
            docs = symbol.structured_docs
            
            if 'summary' in docs:
                parts.append(f"Summary: {docs['summary']}")
            
            if 'params' in docs:
                parts.append("\nParameters:")
                for param in docs['params']:
                    if isinstance(param, dict):
                        name = param.get('name', '')
                        desc = param.get('description', '')
                        parts.append(f"  - {name}: {desc}")
            
            if 'returns' in docs:
                ret = docs['returns']
                if isinstance(ret, dict):
                    parts.append(f"\nReturns: {ret.get('description', '')}")
                else:
                    parts.append(f"\nReturns: {ret}")
            
            if 'example' in docs:
                parts.append(f"\nExample:\n{docs['example']}")
        
        content = '\n'.join(parts)
        
        metadata = {
            'namespace': context.namespace,
            'has_structured_docs': symbol.structured_docs is not None,
            'is_public': context.is_public
        }
        
        return {
            'content': content,
            'content_type': 'documentation',
            'chunk_subtype': 'intent',
            'context_metadata': metadata,
            'start_line': symbol.start_line,
            'end_line': symbol.start_line  # Documentation is at the start
        }
    
    def _extract_symbol_body(
        self,
        file_content: str,
        start_line: int,
        end_line: int
    ) -> str:
        """Extract symbol body from file content."""
        lines = file_content.split('\n')
        
        # Adjust for 0-based indexing
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line)
        
        # Limit to reasonable size
        max_lines = 100
        if end_idx - start_idx > max_lines:
            end_idx = start_idx + max_lines
        
        body_lines = lines[start_idx:end_idx]
        return '\n'.join(body_lines)

