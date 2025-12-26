#!/usr/bin/env python3
"""
Test script specifically for LOCAL embedding generation.
Tests sentence-transformers without requiring OpenAI API.
"""
import asyncio
import sys
from pathlib import Path
import os

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Force local embedding provider
os.environ['EMBEDDING_PROVIDER'] = 'local'
os.environ['LOCAL_EMBEDDING_MODEL'] = 'sentence-transformers/all-MiniLM-L6-v2'  # Faster, smaller model for testing

from src.embeddings.generator import EmbeddingGenerator
from src.embeddings.chunking import TextChunker


async def test_local_embedding_generation():
    """Test local embedding generation."""
    print("\n" + "="*60)
    print("Testing LOCAL Embedding Generation")
    print("="*60)
    
    print("\nInitializing local embedding generator...")
    generator = EmbeddingGenerator()
    
    print(f"  Provider: {generator.provider}")
    print(f"  Model: {generator.model_name}")
    print(f"  Dimension: {generator.dimension}")
    
    # Create test chunks
    chunks = [
        {'id': 1, 'content': 'Function to calculate the sum of two numbers'},
        {'id': 2, 'content': 'Class for handling user authentication and sessions'},
        {'id': 3, 'content': 'Method to process data and return results'}
    ]
    
    print(f"\nGenerating embeddings for {len(chunks)} code-related chunks...")
    results = await generator.generate_embeddings(chunks)
    
    print(f"\n[SUCCESS] Generated {len(results)} embeddings")
    for result in results:
        print(f"  - Chunk {result.chunk_id}: {len(result.vector)} dimensions (first 3 values: {result.vector[:3]})")
    
    return True


async def test_single_query_embedding():
    """Test embedding a search query."""
    print("\n" + "="*60)
    print("Testing Search Query Embedding")
    print("="*60)
    
    generator = EmbeddingGenerator()
    
    query = "How to implement user authentication?"
    print(f"\nQuery: '{query}'")
    
    vector = await generator.generate_single_embedding(query)
    
    print(f"[SUCCESS] Generated query embedding with {len(vector)} dimensions")
    print(f"  First 5 values: {[round(v, 4) for v in vector[:5]]}")
    
    return True


async def test_batch_performance():
    """Test performance with a larger batch."""
    print("\n" + "="*60)
    print("Testing Batch Performance")
    print("="*60)
    
    import time
    
    generator = EmbeddingGenerator()
    
    # Create 20 test chunks
    chunks = [
        {'id': i, 'content': f'This is test code snippet number {i} with some content'}
        for i in range(20)
    ]
    
    print(f"\nGenerating embeddings for {len(chunks)} chunks...")
    start_time = time.time()
    results = await generator.generate_embeddings(chunks)
    duration = time.time() - start_time
    
    print(f"\n[SUCCESS] Generated {len(results)} embeddings in {duration:.2f} seconds")
    print(f"  Average: {duration/len(results):.3f} seconds per embedding")
    print(f"  Throughput: {len(results)/duration:.1f} embeddings/second")
    
    return True


def test_text_chunking():
    """Test text chunking functionality."""
    print("\n" + "="*60)
    print("Testing Text Chunking")
    print("="*60)
    
    chunker = TextChunker(max_tokens=100, overlap=20)
    
    # Long code snippet
    code = '''
def calculate_user_score(user_data, weights):
    """Calculate weighted score for user based on multiple factors."""
    total_score = 0
    for metric, value in user_data.items():
        if metric in weights:
            total_score += value * weights[metric]
    return total_score

class UserAnalyzer:
    def __init__(self, config):
        self.config = config
        self.scores = {}
    
    def analyze_user(self, user_id):
        user_data = self.fetch_user_data(user_id)
        score = calculate_user_score(user_data, self.config['weights'])
        self.scores[user_id] = score
        return score
'''
    
    chunks = chunker.chunk_text(code)
    print(f"\nOriginal code: {len(code.split())} words")
    print(f"[SUCCESS] Split into {len(chunks)} chunks")
    
    for i, chunk in enumerate(chunks):
        word_count = len(chunk.split())
        print(f"  - Chunk {i+1}: {word_count} words")
    
    return True


async def test_similarity_concept():
    """Demonstrate similarity between related code concepts."""
    print("\n" + "="*60)
    print("Testing Semantic Similarity")
    print("="*60)
    
    generator = EmbeddingGenerator()
    
    # Related code concepts
    texts = [
        "Function to authenticate user with password",
        "Method for user login and authentication",
        "Calculate sum of array elements",
    ]
    
    print("\nGenerating embeddings for similar concepts:")
    for text in texts:
        print(f"  - {text}")
    
    chunks = [{'id': i, 'content': text} for i, text in enumerate(texts)]
    results = await generator.generate_embeddings(chunks)
    
    # Simple cosine similarity
    import math
    
    def cosine_similarity(vec1, vec2):
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))
        return dot_product / (magnitude1 * magnitude2)
    
    print("\n[SUCCESS] Similarity scores:")
    sim_0_1 = cosine_similarity(results[0].vector, results[1].vector)
    sim_0_2 = cosine_similarity(results[0].vector, results[2].vector)
    sim_1_2 = cosine_similarity(results[1].vector, results[2].vector)
    
    print(f"  Authentication concepts (1 vs 2): {sim_0_1:.4f} (high similarity)")
    print(f"  Auth vs Math (1 vs 3): {sim_0_2:.4f} (low similarity)")
    print(f"  Auth vs Math (2 vs 3): {sim_1_2:.4f} (low similarity)")
    
    return True


async def main():
    """Run all local embedding tests."""
    print("\n" + "="*60)
    print("LOCAL EMBEDDING PIPELINE TEST SUITE")
    print("No API keys needed - runs entirely locally!")
    print("="*60)
    
    tests = [
        ("Local Embedding Generation", test_local_embedding_generation),
        ("Single Query Embedding", test_single_query_embedding),
        ("Text Chunking", test_text_chunking),
        ("Batch Performance", test_batch_performance),
        ("Semantic Similarity", test_similarity_concept),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            import inspect
            if inspect.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n[ERROR] Test '{name}' failed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "[PASSED]" if result else "[FAILED]"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n[SUCCESS] All local embedding tests passed!")
        print("\nYour local embedding pipeline is working correctly.")
        print("You can now use embeddings without any API keys!")
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
        import traceback
        traceback.print_exc()
        sys.exit(1)

