# Embeddings Pipeline - Quick Start Guide

## TL;DR

```bash
# 1. Install dependencies (already done)
pip install sentence-transformers torch redis

# 2. Test the local embedding pipeline
python scripts/test_local_embeddings.py

# 3. Use in your code
from src.embeddings.generator import EmbeddingGenerator

generator = EmbeddingGenerator()  # Uses local model by default
chunks = [{'id': 1, 'content': 'Your code here'}]
results = await generator.generate_embeddings(chunks)
```

## Quick Examples

### Basic Usage
```python
from src.embeddings.generator import EmbeddingGenerator

# Initialize (uses local model by default)
generator = EmbeddingGenerator()

# Generate embeddings for multiple chunks
chunks = [
    {'id': 1, 'content': 'Function to calculate sum'},
    {'id': 2, 'content': 'Class for user authentication'}
]
results = await generator.generate_embeddings(chunks)

# Each result contains: chunk_id, vector, model_name, model_version, dimension
for result in results:
    print(f"Chunk {result.chunk_id}: {len(result.vector)} dimensions")
```

### Single Query
```python
# Embed a search query
query = "How to implement authentication?"
vector = await generator.generate_single_embedding(query)
# Returns: List[float] with 384 dimensions (for all-MiniLM-L6-v2)
```

### With Caching
```python
from src.embeddings.cache import EmbeddingCache

cache = EmbeddingCache()
content_hash = EmbeddingCache.hash_content(text)

# Check cache
vector = cache.get(content_hash, generator.model_name)
if not vector:
    # Generate and cache
    vector = await generator.generate_single_embedding(text)
    cache.set(content_hash, generator.model_name, vector)
```

### Text Chunking
```python
from src.embeddings.chunking import TextChunker

chunker = TextChunker(max_tokens=512, overlap=50)

# Chunk long text
long_text = "..." # Your long text
chunks = chunker.chunk_text(long_text)

# Chunk code
code = "..." # Your code
code_chunks = chunker.chunk_code(code, max_lines=50)
```

## Configuration

### Local Model (Default - No API Key Needed!)
```bash
EMBEDDING_PROVIDER=local
LOCAL_EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2
```

### OpenAI (Optional)
```bash
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=your_key_here
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

## Available Models

### Fast & Small (Recommended for testing)
```bash
LOCAL_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
# Dimension: 384, Size: ~80MB, Speed: Very Fast
```

### Best Quality (Recommended for production)
```bash
LOCAL_EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2
# Dimension: 768, Size: ~420MB, Speed: Fast
```

## Testing

```bash
# Test local embeddings (no API needed)
python scripts/test_local_embeddings.py

# Run unit tests
pytest tests/unit/test_embedding_generator.py -v

# Run all tests
pytest tests/unit/test_embedding_generator.py tests/integration/test_embedding_pipeline.py -v
```

## Performance

| Operation | Time | Notes |
|-----------|------|-------|
| Single embedding | ~0.003s | Local model |
| Batch of 100 | ~0.3s | Local model |
| Model loading | ~2-3s | First time only |

## Common Patterns

### Batch Processing for Efficiency
```python
# Good - process in batches
chunks = [{'id': i, 'content': texts[i]} for i in range(100)]
results = await generator.generate_embeddings(chunks, batch_size=50)

# Avoid - one at a time
for text in texts:
    await generator.generate_single_embedding(text)  # Slower!
```

### Error Handling
```python
try:
    results = await generator.generate_embeddings(chunks)
except Exception as e:
    logger.error(f"Embedding failed: {e}")
    # Handle error
```

### Semantic Search Example
```python
# 1. Generate embeddings for your code
code_chunks = [
    {'id': 1, 'content': 'Function to authenticate user'},
    {'id': 2, 'content': 'Calculate array sum'},
]
embeddings = await generator.generate_embeddings(code_chunks)

# 2. Embed search query
query = "How to do user authentication?"
query_vector = await generator.generate_single_embedding(query)

# 3. Find similar (using cosine similarity)
import math

def cosine_similarity(v1, v2):
    dot = sum(a*b for a,b in zip(v1, v2))
    mag1 = math.sqrt(sum(a*a for a in v1))
    mag2 = math.sqrt(sum(b*b for b in v2))
    return dot / (mag1 * mag2)

for emb in embeddings:
    similarity = cosine_similarity(query_vector, emb.vector)
    print(f"Chunk {emb.chunk_id}: {similarity:.4f}")
# Output: Chunk 1: 0.7234 (high), Chunk 2: 0.0521 (low)
```

## Troubleshooting

### Model Not Downloading?
```python
# Pre-download manually
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
```

### Out of Memory?
```bash
# Use smaller model
LOCAL_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Or reduce batch size
EMBEDDING_BATCH_SIZE=50
```

### Redis Not Available?
The cache will gracefully degrade - embeddings will still work, just without caching.

## More Information

- Full Documentation: `src/embeddings/README.md`
- API Reference: See README.md
- Test Examples: `scripts/test_local_embeddings.py`
- Integration Tests: `tests/integration/test_embedding_pipeline.py`

## Support

For issues or questions:
1. Check `src/embeddings/README.md` for detailed documentation
2. Run test suite to verify setup: `python scripts/test_local_embeddings.py`
3. Check logs for error details (structured JSON logging)

