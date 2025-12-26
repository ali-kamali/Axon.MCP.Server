# Embeddings Module

This module provides embedding generation capabilities for the Axon MCP Server, supporting both local models (sentence-transformers) and cloud-based models (OpenAI).

## Overview

The embeddings module converts text and code into vector representations that enable semantic search and similarity matching. It includes:

- **Generator**: Creates embeddings using local or OpenAI models
- **Cache**: Redis-based caching to reduce redundant computations
- **Chunking**: Utilities to split large texts into manageable chunks

## Features

✅ **Local Model Support** - Run embeddings without external APIs using sentence-transformers  
✅ **OpenAI Integration** - Optional cloud-based embedding generation  
✅ **Batch Processing** - Efficient processing of multiple chunks  
✅ **Caching** - Redis-based caching to avoid redundant API calls  
✅ **Async Support** - Full async/await support for non-blocking operations  
✅ **Metrics** - Prometheus metrics for monitoring  
✅ **Error Handling** - Comprehensive error handling and retry logic  

## Quick Start

### 1. Basic Usage (Local Model)

```python
from src.embeddings.generator import EmbeddingGenerator

# Initialize generator (uses local model by default)
generator = EmbeddingGenerator()

# Generate embeddings for chunks
chunks = [
    {'id': 1, 'content': 'Function to calculate sum'},
    {'id': 2, 'content': 'Class for user authentication'}
]

results = await generator.generate_embeddings(chunks)

# results contains EmbeddingResult objects with vectors
for result in results:
    print(f"Chunk {result.chunk_id}: {len(result.vector)} dimensions")
```

### 2. Generate Single Embedding

```python
generator = EmbeddingGenerator()

text = "This is a test sentence"
vector = await generator.generate_single_embedding(text)
# vector is a List[float] with embedding values
```

### 3. Using Cache

```python
from src.embeddings.cache import EmbeddingCache

cache = EmbeddingCache()

# Hash the content
content_hash = EmbeddingCache.hash_content("Some text")

# Check cache
cached_vector = cache.get(content_hash, model_name)
if cached_vector is None:
    # Generate and cache
    vector = await generator.generate_single_embedding("Some text")
    cache.set(content_hash, model_name, vector)
```

### 4. Text Chunking

```python
from src.embeddings.chunking import TextChunker

chunker = TextChunker(max_tokens=512, overlap=50)

# Chunk long text
long_text = "..." # Your long text here
chunks = chunker.chunk_text(long_text)

# Chunk code
code = "..." # Your code here
code_chunks = chunker.chunk_code(code, max_lines=50)
```

## Configuration

Configure embedding settings in your `.env` file or environment variables:

```bash
# Embedding Provider (local or openai)
EMBEDDING_PROVIDER=local

# Local Model Settings
LOCAL_EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2
EMBEDDING_BATCH_SIZE=100

# OpenAI Settings (only needed if EMBEDDING_PROVIDER=openai)
OPENAI_API_KEY=your_api_key_here
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSION=1536
```

## Supported Models

### Local Models (sentence-transformers)

| Model | Dimensions | Speed | Quality | Size |
|-------|-----------|-------|---------|------|
| `all-mpnet-base-v2` | 768 | Medium | High | ~420MB |
| `all-MiniLM-L6-v2` | 384 | Fast | Good | ~80MB |
| `all-MiniLM-L12-v2` | 384 | Medium | Good | ~120MB |
| `paraphrase-multilingual-mpnet-base-v2` | 768 | Medium | High (multilingual) | ~970MB |

**Recommended**: `all-mpnet-base-v2` for best quality, `all-MiniLM-L6-v2` for speed.

### OpenAI Models

| Model | Dimensions | Cost |
|-------|-----------|------|
| `text-embedding-3-small` | 1536 | $0.02 / 1M tokens |
| `text-embedding-3-large` | 3072 | $0.13 / 1M tokens |
| `text-embedding-ada-002` | 1536 | $0.10 / 1M tokens |

## Architecture

```
┌─────────────────────────────────────────┐
│         EmbeddingGenerator              │
│                                         │
│  ┌──────────────┐   ┌───────────────┐  │
│  │   OpenAI     │   │    Local      │  │
│  │   Provider   │   │   Provider    │  │
│  │              │   │(Sentence      │  │
│  │              │   │Transformers)  │  │
│  └──────────────┘   └───────────────┘  │
│                                         │
│         ↓                               │
│  ┌──────────────────────────────────┐  │
│  │    EmbeddingResult                │  │
│  │  - chunk_id                       │  │
│  │  - vector: List[float]            │  │
│  │  - model_name                     │  │
│  │  - dimension                      │  │
│  └──────────────────────────────────┘  │
└─────────────────────────────────────────┘
              ↓
    ┌─────────────────┐
    │ EmbeddingCache  │
    │    (Redis)      │
    └─────────────────┘
```

## Performance

### Local Model (all-mpnet-base-v2)

- **Batch of 100 chunks**: ~15-30 seconds (CPU)
- **Single embedding**: ~0.2-0.5 seconds
- **Memory usage**: ~2GB RAM
- **First load**: 3-5 seconds (model loading)

### OpenAI API

- **Batch of 100 chunks**: ~2-5 seconds
- **Single embedding**: ~0.1-0.3 seconds
- **Rate limits**: Varies by tier
- **Cost**: $0.02 per 1M tokens

## Best Practices

### 1. Batch Processing

Always process multiple chunks together for better efficiency:

```python
# Good - batch processing
chunks = [{'id': i, 'content': text} for i, text in enumerate(texts)]
results = await generator.generate_embeddings(chunks)

# Avoid - individual processing
for text in texts:
    await generator.generate_single_embedding(text)  # Slower
```

### 2. Use Caching

Implement caching to avoid regenerating embeddings for identical content:

```python
cache = EmbeddingCache()
content_hash = EmbeddingCache.hash_content(text)

# Check cache first
vector = cache.get(content_hash, model_name)
if vector is None:
    # Generate and cache
    vector = await generator.generate_single_embedding(text)
    cache.set(content_hash, model_name, vector)
```

### 3. Chunk Large Content

Break large files into smaller chunks before embedding:

```python
chunker = TextChunker(max_tokens=512, overlap=50)
chunks = chunker.chunk_text(large_text)

# Convert to format for generator
formatted_chunks = [
    {'id': i, 'content': chunk}
    for i, chunk in enumerate(chunks)
]

results = await generator.generate_embeddings(formatted_chunks)
```

### 4. Error Handling

The generator continues processing even if individual batches fail:

```python
# If one batch fails, others continue
results = await generator.generate_embeddings(chunks)

# Check results length
if len(results) < len(chunks):
    print(f"Warning: Only {len(results)}/{len(chunks)} embeddings generated")
```

## Monitoring

The module exposes Prometheus metrics:

- `embedding_generation_duration_seconds` - Histogram of generation duration
- `embeddings_generated_total` - Counter of embeddings generated (by model and status)

Access metrics at `http://localhost:9090/metrics`

## Testing

Run the test suite:

```bash
# Unit tests
pytest tests/unit/test_embedding_generator.py -v

# Integration tests
pytest tests/integration/test_embedding_pipeline.py -v

# Quick test script
python scripts/test_embeddings.py
```

## Troubleshooting

### Model Download Issues

If sentence-transformers fails to download models:

```bash
# Pre-download the model
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-mpnet-base-v2')"
```

### Memory Issues

For large batches, reduce the batch size:

```python
# In settings.py or .env
EMBEDDING_BATCH_SIZE=50  # Default is 100
```

### Redis Connection Issues

Cache will gracefully degrade if Redis is unavailable:

```python
# Cache operations return None/False if Redis is down
# Generator continues to work without caching
```

### Performance on CPU

For faster CPU inference, install optimized PyTorch:

```bash
# CPU-optimized PyTorch
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

## API Reference

### EmbeddingGenerator

```python
class EmbeddingGenerator:
    def __init__(self)
    async def generate_embeddings(chunks: List[Dict], batch_size: Optional[int]) -> List[EmbeddingResult]
    async def generate_single_embedding(text: str) -> List[float]
```

### EmbeddingCache

```python
class EmbeddingCache:
    def __init__(self)
    def get(content_hash: str, model_name: str) -> Optional[List[float]]
    def set(content_hash: str, model_name: str, embedding: List[float]) -> bool
    @staticmethod
    def hash_content(content: str) -> str
```

### TextChunker

```python
class TextChunker:
    def __init__(max_tokens: int = 512, overlap: int = 50)
    def chunk_text(text: str) -> List[str]
    def chunk_code(code: str, max_lines: int = 50) -> List[str]
```

### EmbeddingResult

```python
@dataclass
class EmbeddingResult:
    chunk_id: int
    vector: List[float]
    model_name: str
    model_version: str
    dimension: int
```

## Related Modules

- **Vector Store** (`src/vector_store/`) - Stores and searches embeddings
- **Knowledge Extraction** (`src/extractors/`) - Extracts chunks for embedding
- **Celery Workers** (`src/workers/`) - Background processing of embeddings

## License

Part of the Axon MCP Server project.

