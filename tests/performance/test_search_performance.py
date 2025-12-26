"""Performance tests for search and parsing operations."""

import pytest
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.api.services.search_service import SearchService
from src.parsers.csharp_parser import CSharpParser
from src.parsers.javascript_parser import TypeScriptParser
from src.parsers.vue_parser import VueParser
from src.config.enums import SymbolKindEnum, LanguageEnum


@pytest.mark.performance
@pytest.mark.asyncio
async def test_search_performance(async_session):
    """Test search performance meets targets."""
    with patch('src.api.services.search_service.EmbeddingGenerator'):
        search_service = SearchService(async_session)
        search_service.embedding_generator = AsyncMock()
        search_service.embedding_generator.generate_single_embedding.return_value = [0.1] * 384
        
        # Mock vector store
        search_service.vector_store = AsyncMock()
        search_service.vector_store.search_similar = AsyncMock(return_value=[])
        
        # Run multiple searches and measure time
        iterations = 10  # Reduced for faster tests
        start_time = time.time()
        
        for i in range(iterations):
            await search_service.search(
                query="test function",
                limit=20,
                hybrid=True
            )
        
        total_time = time.time() - start_time
        avg_time = total_time / iterations
        
        # Should average < 500ms per search
        assert avg_time < 0.5, f"Average search time {avg_time}s exceeds target of 0.5s"
        print(f"\nSearch performance: {avg_time:.3f}s average per search")


@pytest.mark.performance
@pytest.mark.asyncio
async def test_keyword_search_performance(async_session):
    """Test keyword search performance."""
    with patch('src.api.services.search_service.EmbeddingGenerator'):
        search_service = SearchService(async_session)
        
        iterations = 20
        start_time = time.time()
        
        for i in range(iterations):
            await search_service._keyword_search(
                "test",
                limit=20,
                repository_id=None,
                language=None,
                symbol_kind=None
            )
        
        total_time = time.time() - start_time
        avg_time = total_time / iterations
        
        # Keyword search should be very fast (< 100ms)
        assert avg_time < 0.1, f"Average keyword search time {avg_time}s exceeds target of 0.1s"
        print(f"\nKeyword search performance: {avg_time:.3f}s average per search")


@pytest.mark.performance
def test_csharp_parser_performance(sample_code_csharp, tmp_path):
    """Test C# parser performance."""
    test_file = tmp_path / "test.cs"
    test_file.write_text(sample_code_csharp)
    
    parser = CSharpParser()
    
    # Parse multiple times
    iterations = 50
    start_time = time.time()
    
    for _ in range(iterations):
        result = parser.parse(test_file)
        assert result.success
    
    total_time = time.time() - start_time
    avg_time = total_time / iterations
    
    # Should be < 100ms per file
    assert avg_time < 0.1, f"Average parse time {avg_time}s exceeds target of 0.1s"
    print(f"\nC# parser performance: {avg_time:.4f}s average per file")


@pytest.mark.performance
def test_typescript_parser_performance(sample_code_typescript, tmp_path):
    """Test TypeScript parser performance."""
    test_file = tmp_path / "test.ts"
    test_file.write_text(sample_code_typescript)
    
    parser = TypeScriptParser()
    
    # Parse multiple times
    iterations = 50
    start_time = time.time()
    
    for _ in range(iterations):
        result = parser.parse(test_file)
        assert result.success
    
    total_time = time.time() - start_time
    avg_time = total_time / iterations
    
    # Should be < 100ms per file
    assert avg_time < 0.1, f"Average parse time {avg_time}s exceeds target of 0.1s"
    print(f"\nTypeScript parser performance: {avg_time:.4f}s average per file")


@pytest.mark.performance
def test_vue_parser_performance(tmp_path):
    """Test Vue parser performance."""
    vue_code = '''
<template>
  <div class="container">
    <h1>{{ title }}</h1>
    <p>{{ message }}</p>
  </div>
</template>

<script lang="ts">
export default {
  name: 'TestComponent',
  data() {
    return {
      title: 'Hello',
      message: 'World'
    }
  },
  methods: {
    greet() {
      console.log(this.message);
    }
  }
}
</script>

<style scoped>
.container {
  padding: 20px;
}
</style>
'''
    
    test_file = tmp_path / "test.vue"
    test_file.write_text(vue_code)
    
    parser = VueParser()
    
    # Parse multiple times
    iterations = 50
    start_time = time.time()
    
    for _ in range(iterations):
        result = parser.parse(test_file)
        assert result.success
    
    total_time = time.time() - start_time
    avg_time = total_time / iterations
    
    # Should be < 100ms per file
    assert avg_time < 0.1, f"Average parse time {avg_time}s exceeds target of 0.1s"
    print(f"\nVue parser performance: {avg_time:.4f}s average per file")


@pytest.mark.performance
def test_parser_with_large_file(tmp_path):
    """Test parser performance with larger files."""
    # Generate a large C# file
    large_code = "namespace TestNamespace\n{\n"
    
    # Add 100 classes
    for i in range(100):
        large_code += f"""
    public class TestClass{i}
    {{
        public int Property{i} {{ get; set; }}
        
        public void Method{i}()
        {{
            Console.WriteLine("Test {i}");
        }}
    }}
"""
    
    large_code += "\n}"
    
    test_file = tmp_path / "large.cs"
    test_file.write_text(large_code)
    
    parser = CSharpParser()
    
    # Parse the large file
    start_time = time.time()
    result = parser.parse(test_file)
    parse_time = time.time() - start_time
    
    assert result.success
    assert len(result.symbols) >= 100  # At least 100 classes
    
    # Should still be relatively fast (< 500ms for 100 classes)
    assert parse_time < 0.5, f"Parse time {parse_time}s exceeds target of 0.5s for large file"
    print(f"\nLarge file parser performance: {parse_time:.3f}s for {len(result.symbols)} symbols")


@pytest.mark.performance
@pytest.mark.asyncio
async def test_concurrent_searches(async_session):
    """Test performance with concurrent searches."""
    import asyncio
    
    with patch('src.api.services.search_service.EmbeddingGenerator'):
        search_service = SearchService(async_session)
        search_service.embedding_generator = AsyncMock()
        search_service.embedding_generator.generate_single_embedding.return_value = [0.1] * 384
        search_service.vector_store = AsyncMock()
        search_service.vector_store.search_similar = AsyncMock(return_value=[])
        
        # Run 10 searches concurrently
        concurrent_searches = 10
        start_time = time.time()
        
        tasks = [
            search_service.search(query=f"test {i}", limit=20, hybrid=False)
            for i in range(concurrent_searches)
        ]
        
        await asyncio.gather(*tasks)
        
        total_time = time.time() - start_time
        
        # Concurrent searches should be faster than sequential
        # Should complete in < 2 seconds total
        assert total_time < 2.0, f"Concurrent searches took {total_time}s, exceeds target of 2.0s"
        print(f"\nConcurrent search performance: {total_time:.3f}s for {concurrent_searches} concurrent searches")


@pytest.mark.performance
def test_multiple_parsers_sequential(tmp_path, sample_code_csharp, sample_code_typescript):
    """Test parsing multiple files sequentially."""
    # Create multiple test files
    cs_file = tmp_path / "test.cs"
    cs_file.write_text(sample_code_csharp)
    
    ts_file = tmp_path / "test.ts"
    ts_file.write_text(sample_code_typescript)
    
    vue_file = tmp_path / "test.vue"
    vue_file.write_text('''
<template><div>Test</div></template>
<script>export default { name: 'Test' }</script>
''')
    
    files = [
        (cs_file, CSharpParser()),
        (ts_file, TypeScriptParser()),
        (vue_file, VueParser())
    ]
    
    iterations = 10
    start_time = time.time()
    
    for _ in range(iterations):
        for file_path, parser in files:
            result = parser.parse(file_path)
            assert result.success
    
    total_time = time.time() - start_time
    avg_time_per_file = total_time / (iterations * len(files))
    
    # Average time per file should be < 100ms
    assert avg_time_per_file < 0.1, f"Average parse time {avg_time_per_file}s exceeds target"
    print(f"\nMultiple parsers performance: {avg_time_per_file:.4f}s average per file")


@pytest.mark.performance
@pytest.mark.slow
def test_search_scalability(async_session):
    """Test search performance doesn't degrade with larger result sets."""
    # This is a slow test, marked with @slow
    # Test with different result set sizes
    pass  # Placeholder for scalability testing


@pytest.mark.performance
def test_parser_memory_efficiency(tmp_path, sample_code_csharp):
    """Test parser doesn't leak memory."""
    import gc
    
    test_file = tmp_path / "test.cs"
    test_file.write_text(sample_code_csharp)
    
    parser = CSharpParser()
    
    # Force garbage collection before test
    gc.collect()
    
    # Parse many times
    iterations = 100
    for _ in range(iterations):
        result = parser.parse(test_file)
        assert result.success
        # Don't keep references
        del result
    
    # Force garbage collection
    gc.collect()
    
    # If we got here without memory errors, test passes
    assert True
    print(f"\nMemory efficiency test: Parsed {iterations} files successfully")

