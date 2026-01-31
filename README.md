# Scalable RAG Ingestion Pipeline

A production-ready document ingestion service for RAG (Retrieval-Augmented Generation) systems with multi-tenancy, async processing, and scalable architecture.

## Features

- **Multi-tenant Support**: Strict data isolation between tenants
- **Async Processing**: Distributed workers for text extraction, chunking, and embedding
- **Fairness Mechanisms**: Per-tenant queues with round-robin scheduling
- **Fault Tolerance**: Retry logic with exponential backoff and intermediate storage
- **Scalable Architecture**: Designed to handle 1M+ documents across multiple tenants
- **Vector Search**: Semantic search using Qdrant vector database

## Documentation

| Document | Description |
|----------|-------------|
| **[DESIGN.md](DESIGN.md)** | Complete design document with architecture diagrams, ER diagrams, design decisions, trade-offs, and scalability strategy |
| **[terraform/README.md](terraform/README.md)** | AWS deployment guide using Terraform |
| **[API Docs](http://localhost:8000/docs)** | Interactive Swagger documentation (after starting services) |

## Architecture

The system consists of:

- **API Service**: FastAPI application for upload and search endpoints
- **Workers**: Distributed workers for processing pipeline
  - Text Extractor: Extracts text from PDF and TXT files
  - Chunker: Segments text into overlapping chunks
  - Embedder: Generates embeddings and stores in Qdrant
- **Storage**: 
  - PostgreSQL: Metadata and job tracking
  - Qdrant: Vector database for semantic search
  - MinIO: Object storage for files and intermediate data
  - Redis: Job queue for async processing

## Prerequisites

- Docker and Docker Compose
- No API keys required (uses open-source embedding models)

## Quick Start

1. **Clone the repository**

```bash
git clone <repository-url>
cd Scalable-RAG
```

2. **Set environment variables (optional)**

Create a `.env` file to customize the embedding model:

```bash
# Optional: Change embedding model (default: BAAI/bge-small-en-v1.5)
# Other options: all-MiniLM-L6-v2, all-mpnet-base-v2, BAAI/bge-base-en-v1.5
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
```

3. **Start the services**

```bash
docker-compose up -d
```

This will start:
- PostgreSQL (port 5432)
- Qdrant (ports 6333, 6334)
- Redis (port 6379)
- MinIO (ports 9000, 9001)
- API service (port 8000)
- Workers (text extractor, chunker, embedder)

4. **Access the services**

- API Documentation: http://localhost:8000/docs
- MinIO Console: http://localhost:9001 (minioadmin/minioadmin)
- Qdrant Dashboard: http://localhost:6333/dashboard

## API Usage

### Authentication

The system has **two authentication mechanisms**:

#### 1. Tenant Authentication (External Customers)
- **Header**: `X-API-Key`
- **Scope**: Own tenant's documents only
- **Endpoints**: Upload, Search, Status

Default test tenant API key: `test_api_key_123`

#### 2. Internal Service Authentication (System Components)
- **Header**: `X-Internal-Token`
- **Scope**: Cross-tenant access (elevated privileges)
- **Endpoints**: Admin, Stats, Tenant Management

Default internal token: `internal_service_secret_token`

### Tenant Endpoints

### Upload a Single File

```bash
curl -X POST "http://localhost:8000/upload/single" \
  -H "X-API-Key: test_api_key_123" \
  -F "file=@document.pdf"
```

Response:
```json
{
  "document_id": "uuid",
  "filename": "document.pdf",
  "status": "pending",
  "message": "File uploaded successfully and queued for processing"
}
```

### Bulk Upload

```bash
curl -X POST "http://localhost:8000/upload/bulk" \
  -H "X-API-Key: test_api_key_123" \
  -F "files=@file1.pdf" \
  -F "files=@file2.txt"
```

### Check Document Status

```bash
curl -X GET "http://localhost:8000/status/{document_id}" \
  -H "X-API-Key: test_api_key_123"
```

Response:
```json
{
  "document_id": "uuid",
  "status": "completed",
  "progress": {
    "extract": {"status": "completed"},
    "chunk": {"status": "completed"},
    "embed": {"status": "completed"}
  }
}
```

### Delete a Document

```bash
curl -X DELETE "http://localhost:8000/documents/{document_id}" \
  -H "X-API-Key: test_api_key_123"
```

Response:
```json
{
  "document_id": "uuid",
  "deleted": true,
  "message": "Document and all associated data deleted successfully",
  "chunks_deleted": 5,
  "vectors_deleted": 5
}
```

### Get Tenant Metrics

```bash
curl -X GET "http://localhost:8000/metrics/me" \
  -H "X-API-Key: test_api_key_123"
```

Response:
```json
{
  "tenant_id": "uuid",
  "tenant_name": "test_tenant",
  "document_count": 10,
  "chunk_count": 50,
  "storage_used_bytes": 1048576,
  "last_upload": "2026-01-30T12:00:00Z",
  "rate_limit": 100,
  "current_rate": 5
}
```

### Search Documents

```bash
curl -X POST "http://localhost:8000/search" \
  -H "X-API-Key: test_api_key_123" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is machine learning?",
    "limit": 10,
    "score_threshold": 0.7
  }'
```

Response:
```json
{
  "results": [
    {
      "chunk_id": "uuid",
      "document_id": "uuid",
      "tenant_id": "uuid",
      "filename": "document.pdf",
      "text": "Machine learning is...",
      "score": 0.95,
      "metadata": {}
    }
  ],
  "total": 1,
  "query": "What is machine learning?"
}
```

### Internal Service Endpoints

These endpoints require `X-Internal-Token` header and provide cross-tenant access for system services.

#### Create a New Tenant

```bash
curl -X POST "http://localhost:8000/internal/tenants" \
  -H "X-Internal-Token: internal_service_secret_token" \
  -H "Content-Type: application/json" \
  -d '{"name": "new_customer", "rate_limit": 100}'
```

Response:
```json
{
  "tenant_id": "uuid",
  "name": "new_customer",
  "api_key": "new_customer_ABC123...",
  "rate_limit": 100,
  "message": "Save the API key - shown only once!"
}
```

#### List All Tenants

```bash
curl "http://localhost:8000/internal/tenants" \
  -H "X-Internal-Token: internal_service_secret_token"
```

#### Get System Statistics

```bash
curl "http://localhost:8000/internal/stats" \
  -H "X-Internal-Token: internal_service_secret_token"
```

#### Cross-Tenant Document Search (Internal Only)

```bash
curl -X POST "http://localhost:8000/internal/search?query=machine+learning&limit=10" \
  -H "X-Internal-Token: internal_service_secret_token"
```

#### List All Documents (Cross-Tenant)

```bash
curl "http://localhost:8000/internal/documents?limit=50" \
  -H "X-Internal-Token: internal_service_secret_token"
```

## Project Structure

```
Scalable-RAG/
├── api/                    # FastAPI application
│   ├── main.py            # Application entry point
│   ├── routes/            # API endpoints
│   ├── models/            # Pydantic models
│   ├── services/          # Business logic services
│   └── Dockerfile
├── workers/               # Processing workers
│   ├── text_extractor/    # PDF/TXT extraction
│   ├── chunker/           # Text chunking
│   ├── embedder/          # Embedding generation
│   └── Dockerfile
├── shared/                # Shared utilities
│   ├── config.py          # Configuration
│   ├── models.py          # Shared models
│   └── queue.py           # Queue utilities
├── migrations/            # Database migrations
│   └── init.sql
├── docker-compose.yml     # Service orchestration
├── README.md              # This file
└── DESIGN.md              # Design document
```

## Configuration

Key configuration options in `shared/config.py`:

- `CHUNK_SIZE`: Size of text chunks (default: 512 tokens)
- `CHUNK_OVERLAP`: Overlap between chunks (default: 50 tokens)
- `MAX_RETRIES`: Maximum retry attempts (default: 3)
- `EMBEDDING_MODEL`: Embedding model (default: BAAI/bge-small-en-v1.5)
- `MAX_FILE_SIZE`: Maximum file size (default: 100MB)

## Multi-Tenancy

The system implements multi-tenancy using:

1. **Qdrant**: Single collection with `tenant_id` in payload metadata
2. **PostgreSQL**: All tables include `tenant_id` for filtering
3. **Queues**: Per-tenant queues for fairness
4. **Authentication**: API key-based tenant identification

All queries are automatically filtered by tenant ID to ensure data isolation.

## Fairness Mechanisms

- **Per-Tenant Queues**: Each tenant has separate queues for each job type
- **Round-Robin Scheduling**: Workers process jobs from different tenants in round-robin fashion
- **Rate Limiting**: Configurable rate limits per tenant (default: 100 requests/minute)

## Scaling Considerations

The system is designed to scale to:

- **1M+ total documents** across all tenants
- **50K documents per tenant**
- **50K documents per tenant in < 24 hours**

To scale:

1. **Horizontal Scaling**: Add more worker instances
2. **Qdrant Cluster**: Use Qdrant cluster mode for large vector collections
3. **PostgreSQL Replicas**: Use read replicas for search queries
4. **Load Balancing**: Add load balancer for API service

## Development

### Running Locally

1. Install dependencies:

```bash
pip install -r api/requirements.txt
pip install -r workers/requirements.txt
```

2. Start services (PostgreSQL, Qdrant, Redis, MinIO):

```bash
docker-compose up -d postgres qdrant redis minio
```

3. Run API service:

```bash
cd api
uvicorn main:app --reload
```

4. Run workers:

```bash
python -m workers.text_extractor.worker
python -m workers.chunker.worker
python -m workers.embedder.worker
```

### Testing

Run tests:

```bash
pytest tests/
```

## Production Considerations

For production deployment:

1. **Security**:
   - Use HTTPS
   - Implement proper API key hashing (bcrypt)
   - Add input validation and file size limits
   - Use secrets management

2. **Monitoring**:
   - Add Prometheus metrics
   - Set up Grafana dashboards
   - Implement structured logging with correlation IDs

3. **Reliability**:
   - Set up automated backups for PostgreSQL and Qdrant
   - Implement health checks
   - Add circuit breakers

4. **Performance**:
   - Use connection pooling
   - Implement caching (Redis)
   - Optimize database queries

5. **CI/CD**:
   - Automated testing
   - Deployment pipelines
   - Load testing

## License

MIT License
