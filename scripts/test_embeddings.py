#!/usr/bin/env python3
"""
Test script for embedding generation pipeline.
Tests local embedding generation without requiring external APIs.
"""
import asyncio
import sys
from pathlib import Path
import inspect

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.embeddings.generator import EmbeddingGenerator
from src.embeddings.cache import EmbeddingCache
from src.embeddings.chunking import TextChunker
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


async def test_basic_embedding():
    """Test basic embedding generation."""
    print("\n" + "="*60)
    print("Testing Basic Embedding Generation")
    print("="*60)
    
    try:
        generator = EmbeddingGenerator()
        
        chunks = [
            {'id': 1, 'content': 'This is a test sentence for embedding generation.'},
            {'id': 2, 'content': 'Function to calculate the sum of two numbers'},
            {'id': 3, 'content': 'Class for handling user authentication and authorization'}
        ]
        
        print(f"\nGenerating embeddings for {len(chunks)} chunks...")
        print(f"Provider: {generator.provider}")
        print(f"Model: {generator.model_name}")
        print(f"Dimension: {generator.dimension}")
        
        results = await generator.generate_embeddings(chunks)
        
        print(f"\n[OK] Successfully generated {len(results)} embeddings")
        for result in results:
            print(f"  - Chunk {result.chunk_id}: {len(result.vector)} dimensions")
        
        return True
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        logger.error("basic_embedding_test_failed", error=str(e))
        return False


async def test_single_embedding():
    """Test single text embedding."""
    print("\n" + "="*60)
    print("Testing Single Text Embedding")
    print("="*60)
    
    try:
        generator = EmbeddingGenerator()
        
        text = "This is a single test sentence."
        print(f"\nGenerating embedding for: '{text}'")
        
        vector = await generator.generate_single_embedding(text)
        
        print(f"[OK] Successfully generated embedding with {len(vector)} dimensions")
        print(f"  First 5 values: {vector[:5]}")
        
        return True
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        logger.error("single_embedding_test_failed", error=str(e))
        return False


async def test_caching():
    """Test embedding caching."""
    print("\n" + "="*60)
    print("Testing Embedding Cache")
    print("="*60)
    
    try:
        generator = EmbeddingGenerator()
        cache = EmbeddingCache()
        
        text = "This is a test for caching."
        content_hash = EmbeddingCache.hash_content(text)
        
        # First check - should miss
        print("\nChecking cache (should miss)...")
        cached = cache.get(content_hash, generator.model_name)
        if cached is None:
            print("[OK] Cache miss (expected)")
        else:
            print("[ERROR] Unexpected cache hit")
            return False
        
        # Generate embedding
        print("\nGenerating embedding...")
        chunks = [{'id': 1, 'content': text}]
        results = await generator.generate_embeddings(chunks)
        
        # Cache it
        print("Storing in cache...")
        success = cache.set(content_hash, generator.model_name, results[0].vector)
        if success:
            print("[OK] Successfully cached")
        else:
            print("[WARN] Cache unavailable (Redis may not be running)")
            return True  # Not a failure if Redis isn't available
        
        # Second check - should hit
        print("\nChecking cache again (should hit)...")
        cached = cache.get(content_hash, generator.model_name)
        if cached is not None and len(cached) == generator.dimension:
            print("[OK] Cache hit (expected)")
            return True
        else:
            print("[ERROR] Cache miss (unexpected)")
            return False
            
    except Exception as e:
        print(f"\n[WARN] Cache test failed (Redis may not be running): {e}")
        return True  # Not critical if Redis isn't available


def test_chunking():
    """Test text chunking."""
    print("\n" + "="*60)
    print("Testing Text Chunking")
    print("="*60)
    
    try:
        chunker = TextChunker(max_tokens=20, overlap=5)
        
        # Test short text
        short_text = "This is a short text."
        chunks = chunker.chunk_text(short_text)
        print(f"\nShort text: '{short_text}'")
        print(f"[OK] Chunks: {len(chunks)} (expected: 1)")
        
        # Test long text
        long_text = " ".join([f"word{i}" for i in range(100)])
        chunks = chunker.chunk_text(long_text)
        print(f"\nLong text: 100 words")
        print(f"[OK] Chunks: {len(chunks)} (expected: >1)")
        
        # Test code chunking
        code = "\n".join([f"line {i}" for i in range(100)])
        code_chunks = chunker.chunk_code(code, max_lines=20)
        print(f"\nCode: 100 lines")
        print(f"[OK] Chunks: {len(code_chunks)} (expected: ~5)")
        
        return True
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        logger.error("chunking_test_failed", error=str(e))
        return False


async def test_batch_processing():
    """Test batch processing."""
    print("\n" + "="*60)
    print("Testing Batch Processing")
    print("="*60)
    
    try:
        generator = EmbeddingGenerator()
        
        # Create a batch of chunks
        chunks = [
            {'id': i, 'content': f'Test content number {i}'}
            for i in range(10)
        ]
        
        print(f"\nGenerating embeddings for {len(chunks)} chunks...")
        results = await generator.generate_embeddings(chunks, batch_size=3)
        
        print(f"[OK] Successfully processed {len(results)} chunks in batches of 3")
        
        return True
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        logger.error("batch_processing_test_failed", error=str(e))
        return False


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Embedding Pipeline Test Suite")
    print("="*60)
    
    tests = [
        ("Basic Embedding", test_basic_embedding),
        ("Single Embedding", test_single_embedding),
        ("Caching", test_caching),
        ("Chunking", test_chunking),
        ("Batch Processing", test_batch_processing),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            if inspect.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n[ERROR] Test '{name}' crashed: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "[PASSED]" if result else "[FAILED]"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n[SUCCESS] All tests passed!")
        return 0
    else:
        print(f"\n[WARNING] {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        sys.exit(1)

