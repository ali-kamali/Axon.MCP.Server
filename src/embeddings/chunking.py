from typing import List
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class TextChunker:
    """Split text into chunks suitable for embedding."""
    
    def __init__(self, max_tokens: int = 512, overlap: int = 50):
        """
        Initialize chunker.
        
        Args:
            max_tokens: Maximum tokens per chunk
            overlap: Overlap tokens between chunks
        """
        self.max_tokens = max_tokens
        self.overlap = overlap
    
    def chunk_text(self, text: str) -> List[str]:
        """
        Split text into overlapping chunks.
        
        Args:
            text: Text to chunk
            
        Returns:
            List of text chunks
        """
        # Simple word-based chunking (could be improved with proper tokenization)
        words = text.split()
        
        if len(words) <= self.max_tokens:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(words):
            end = start + self.max_tokens
            chunk_words = words[start:end]
            chunks.append(' '.join(chunk_words))
            
            # Move start forward with overlap
            start = end - self.overlap
            
            if start >= len(words):
                break
        
        logger.debug("text_chunked", original_words=len(words), chunks=len(chunks))
        return chunks
    
    def chunk_code(self, code: str, max_lines: int = 50) -> List[str]:
        """
        Split code into logical chunks.
        
        Args:
            code: Code to chunk
            max_lines: Maximum lines per chunk
            
        Returns:
            List of code chunks
        """
        lines = code.split('\n')
        
        if len(lines) <= max_lines:
            return [code]
        
        chunks = []
        for i in range(0, len(lines), max_lines):
            chunk_lines = lines[i:i + max_lines]
            chunks.append('\n'.join(chunk_lines))
        
        return chunks

