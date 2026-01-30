# Embedding Model Migration: OpenAI → Open-Source

## Summary

The system has been updated to use open-source embedding models instead of OpenAI. This eliminates the need for API keys and reduces costs.

## Changes Made

### 1. Configuration (`shared/config.py`)
- **Removed**: `OPENAI_API_KEY`, `OPENAI_EMBEDDING_MODEL`, `OPENAI_BATCH_SIZE`
- **Added**: `EMBEDDING_MODEL`, `EMBEDDING_BATCH_SIZE`
- **Updated**: `QDRANT_VECTOR_SIZE` from 1536 → 384 (for BAAI/bge-small-en-v1.5)

### 2. Embedding Worker (`workers/embedder/worker.py`)
- **Removed**: OpenAI client initialization
- **Added**: SentenceTransformer model loading
- **Updated**: `generate_embeddings()` now uses `sentence-transformers`

### 3. Search Endpoint (`api/routes/search.py`)
- **Removed**: OpenAI client and API key checks
- **Added**: SentenceTransformer model (loaded once at startup)
- **Updated**: Query embedding generation uses local model

### 4. Dependencies
- **Removed**: `openai` package
- **Added**: `sentence-transformers==2.2.2`, `torch==2.1.0`

### 5. Docker Compose
- **Removed**: `OPENAI_API_KEY` environment variable
- **Added**: `EMBEDDING_MODEL` environment variable (default: `BAAI/bge-small-en-v1.5`)

## Default Model

**BAAI/bge-small-en-v1.5**
- **Dimensions**: 384
- **Size**: ~130MB
- **Performance**: Good balance of speed and quality
- **License**: MIT

## Alternative Models

You can change the model by setting the `EMBEDDING_MODEL` environment variable:

### Fast & Small (384 dimensions)
- `all-MiniLM-L6-v2` - Very fast, good for high throughput
- `BAAI/bge-small-en-v1.5` - Better quality than MiniLM (default)

### Higher Quality (768 dimensions)
- `all-mpnet-base-v2` - Better quality, slower
- `BAAI/bge-base-en-v1.5` - High quality, good performance

**Note**: If changing to a 768-dimension model, also update `QDRANT_VECTOR_SIZE` in `shared/config.py`

## Migration Steps

1. **Rebuild Docker images** (required for new dependencies):
   ```bash
   docker-compose down
   docker-compose build --no-cache
   docker-compose up -d
   ```

2. **Recreate Qdrant collection** (vector size changed):
   - The collection will be automatically recreated with the new vector size
   - Existing documents will need to be re-ingested

3. **Optional: Change model**:
   ```bash
   # In .env file
   EMBEDDING_MODEL=all-MiniLM-L6-v2
   ```

## Benefits

✅ **No API costs** - Completely free to run
✅ **No rate limits** - Process as many documents as needed
✅ **Privacy** - All processing happens locally
✅ **Faster** - No network latency for embedding generation
✅ **Customizable** - Easy to switch between models

## Performance Notes

- First embedding generation may be slower (model loading)
- Subsequent embeddings are fast (model cached in memory)
- Batch processing is supported for efficiency
- GPU acceleration available if CUDA is installed (automatic)

## Troubleshooting

**Model download issues**: The model downloads automatically on first use. If you have network issues, you can pre-download:
```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('BAAI/bge-small-en-v1.5')
```

**Memory issues**: If running out of memory, use a smaller model like `all-MiniLM-L6-v2`

**Vector size mismatch**: If you see errors about vector dimensions, ensure `QDRANT_VECTOR_SIZE` matches your model's output size
