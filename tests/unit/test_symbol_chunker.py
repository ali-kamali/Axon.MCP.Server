"""Tests for symbol-based chunker."""

import pytest
from unittest.mock import Mock, AsyncMock
from src.embeddings.symbol_chunker import SymbolChunker, ChunkConfig
from src.embeddings.chunk_context import ChunkContext
from src.database.models import Symbol, File
from src.config.enums import SymbolKindEnum, LanguageEnum


class TestSymbolChunker:
    """Test symbol-based chunking functionality."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.config = ChunkConfig(
            max_token_size=8000,
            context_lines_before=5,
            context_lines_after=5,
            include_parent_context=True,
            include_imports=True,
            include_relationships=True,
            separate_docs_chunks=True
        )
        self.chunker = SymbolChunker(self.config)
    
    def test_create_code_chunk(self):
        """Test creation of code-focused chunk."""
        # Create mock symbol
        symbol = Mock(spec=Symbol)
        symbol.id = 1
        symbol.name = "GetUser"
        symbol.kind = SymbolKindEnum.METHOD
        symbol.signature = "public User GetUser(int id)"
        symbol.documentation = "Retrieves a user by ID"
        symbol.start_line = 10
        symbol.end_line = 20
        
        # Create mock file
        file = Mock(spec=File)
        file.id = 1
        file.path = "Services/UserService.cs"
        
        # Create context
        context = ChunkContext(
            file_path=file.path,
            namespace="MyApp.Services",
            imports=["System", "System.Linq"],
            parent_class={"name": "UserService", "signature": "public class UserService"},
            calls=["FindUserById", "ValidateUser"],
            implements=["IUserService"],
            is_public=True,
            complexity=5
        )
        
        # Create chunks
        chunks = self.chunker.create_chunks_for_symbol(symbol, file, context)
        
        # Should create at least one chunk
        assert len(chunks) > 0
        
        # Check code chunk
        code_chunk = next((c for c in chunks if c['chunk_subtype'] == 'implementation'), None)
        assert code_chunk is not None
        
        # Verify content includes expected information
        content = code_chunk['content']
        assert file.path in content
        assert context.namespace in content
        assert symbol.signature in content
        
        # Check metadata
        metadata = code_chunk['context_metadata']
        assert metadata['namespace'] == "MyApp.Services"
        assert len(metadata['imports']) > 0
        assert len(metadata['calls']) > 0
        assert metadata['is_public'] == True
        assert metadata['complexity'] == 5
    
    def test_create_documentation_chunk(self):
        """Test creation of documentation-focused chunk."""
        # Create symbol with rich documentation
        symbol = Mock(spec=Symbol)
        symbol.id = 1
        symbol.name = "CalculateTotal"
        symbol.kind = SymbolKindEnum.FUNCTION
        symbol.signature = "function calculateTotal(items: Item[]): number"
        symbol.documentation = "Calculates the total price of items including tax"
        symbol.structured_docs = {
            'description': 'Calculates the total price',
            'params': [
                {'name': 'items', 'type': 'Item[]', 'description': 'Array of items'}
            ],
            'returns': {'type': 'number', 'description': 'Total price with tax'}
        }
        symbol.start_line = 5
        symbol.end_line = 15
        
        file = Mock(spec=File)
        file.path = "utils/pricing.ts"
        
        context = ChunkContext(
            file_path=file.path,
            namespace="utils",
            is_public=True
        )
        
        # Create chunks with separate docs enabled
        chunks = self.chunker.create_chunks_for_symbol(symbol, file, context)
        
        # Should create a documentation chunk
        doc_chunk = next((c for c in chunks if c['chunk_subtype'] == 'intent'), None)
        assert doc_chunk is not None
        
        # Check documentation content
        content = doc_chunk['content']
        assert symbol.name in content
        assert symbol.documentation in content
        assert 'Parameters' in content or 'params' in content.lower()
        assert 'Returns' in content or 'returns' in content.lower()
    
    def test_no_docs_creates_single_chunk(self):
        """Test that symbols without docs create only code chunk."""
        symbol = Mock(spec=Symbol)
        symbol.id = 1
        symbol.name = "helper"
        symbol.kind = SymbolKindEnum.FUNCTION
        symbol.signature = "def helper(): pass"
        symbol.documentation = None
        symbol.structured_docs = None
        symbol.start_line = 1
        symbol.end_line = 2
        
        file = Mock(spec=File)
        file.path = "utils.py"
        
        context = ChunkContext(file_path=file.path)
        
        chunks = self.chunker.create_chunks_for_symbol(symbol, file, context)
        
        # Should only have code chunk
        assert len(chunks) == 1
        assert chunks[0]['chunk_subtype'] == 'implementation'
    
    def test_include_parent_context(self):
        """Test that parent class context is included."""
        symbol = Mock(spec=Symbol)
        symbol.id = 1
        symbol.name = "Save"
        symbol.kind = SymbolKindEnum.METHOD
        symbol.signature = "public void Save()"
        symbol.documentation = "Saves changes"
        symbol.start_line = 10
        symbol.end_line = 15
        
        file = Mock(spec=File)
        file.path = "Repository.cs"
        
        context = ChunkContext(
            file_path=file.path,
            parent_class={
                'name': 'UserRepository',
                'kind': 'class',
                'signature': 'public class UserRepository : IRepository'
            }
        )
        
        chunks = self.chunker.create_chunks_for_symbol(symbol, file, context)
        
        code_chunk = next((c for c in chunks if c['chunk_subtype'] == 'implementation'), None)
        assert code_chunk is not None
        
        # Should mention parent class
        content = code_chunk['content']
        assert 'UserRepository' in content or 'In class' in content
    
    def test_include_relationships(self):
        """Test that relationships are included in context."""
        symbol = Mock(spec=Symbol)
        symbol.id = 1
        symbol.name = "ProcessOrder"
        symbol.kind = SymbolKindEnum.METHOD
        symbol.signature = "public void ProcessOrder(Order order)"
        symbol.documentation = "Processes an order"
        symbol.start_line = 20
        symbol.end_line = 40
        
        file = Mock(spec=File)
        file.path = "OrderService.cs"
        
        context = ChunkContext(
            file_path=file.path,
            calls=["ValidateOrder", "CalculateTotal", "SaveOrder"],
            implements=["IOrderProcessor"],
            inherits_from=["BaseService"]
        )
        
        chunks = self.chunker.create_chunks_for_symbol(symbol, file, context)
        
        code_chunk = next((c for c in chunks if c['chunk_subtype'] == 'implementation'), None)
        assert code_chunk is not None
        
        content = code_chunk['content']
        metadata = code_chunk['context_metadata']
        
        # Check calls are included
        assert len(metadata['calls']) == 3
        assert 'ValidateOrder' in metadata['calls']
        
        # Check implements/inherits
        assert len(metadata['implements']) == 1
        assert len(metadata['inherits_from']) == 1

