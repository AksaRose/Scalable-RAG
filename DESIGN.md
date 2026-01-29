# Design Document: Scalable RAG Ingestion Pipeline

## Overview

This document describes the design decisions, architecture, and trade-offs for the Scalable RAG Ingestion Pipeline.

## Architecture

### System Components

1. **API Service** (FastAPI)
   - Handles file uploads (single and bulk)
   - Provides search endpoints
   - Manages authentication and authorization

2. **Processing Workers**
   - **Text Extractor**: Extracts text from PDF and TXT files
   - **Chunker**: Segments text into overlapping chunks
   - **Embedder**: Generates embeddings and stores in Qdrant

3. **Storage Systems**
   - **PostgreSQL**: Metadata, job tracking, tenant management
   - **Qdrant**: Vector database for semantic search
   - **MinIO**: Object storage for files and intermediate data
   - **Redis**: Job queue for async processing

### Data Flow

```
Upload → API → Object Storage → Queue → Text Extractor → Chunker → Embedder → Qdrant
                                                                    ↓
                                                              Parquet Storage
```

## Key Design Decisions

### 1. Multi-Tenancy in Qdrant

**Decision**: Single collection with `tenant_id` in payload metadata

**Rationale**:
- Better resource utilization (shared collection)
- Easier management (single collection to maintain)
- Simpler cross-tenant analytics
- Avoids collection limit concerns at scale

**Isolation**: All queries filtered by `tenant_id` at application level

**Alternative Considered**: Separate collections per tenant
- **Rejected** because: Collection limits, harder management, resource waste

### 2. Chunking Strategy

**Decision**: Overlapping semantic chunks with configurable size

**Parameters**:
- Chunk size: 512-1024 tokens (default: 512)
- Overlap: 10-20% (default: 50 tokens)
- Boundary detection: Sentence-aware breaking

**Rationale**:
- Overlap preserves context across chunk boundaries
- Sentence-aware breaking improves semantic coherence
- Configurable size allows optimization per use case

### 3. Embedding Strategy

**Decision**: OpenAI embeddings with batch processing and intermediate storage

**Model**: `text-embedding-3-small` (1536 dimensions)

**Batch Processing**: 100-500 chunks per batch

**Intermediate Storage**: Parquet files before bulk insert
- **Benefits**: Fault tolerance, retry capability, data recovery

### 4. Fairness Mechanism

**Decision**: Per-tenant queues with round-robin scheduling

**Implementation**:
- Separate Redis sorted sets per tenant and job type
- Workers dequeue in round-robin across tenant queues
- Priority-based processing within tenant queues

**Rate Limiting**: Token bucket algorithm (configurable per tenant)

**Bulk Upload Handling**: Throttled to prevent starvation

### 5. Queue System

**Decision**: Redis with sorted sets for priority queues

**Rationale**:
- Simple and fast
- Supports priority-based processing
- Easy to implement per-tenant queues

**Alternative Considered**: Kafka
- **Rejected** because: Overkill for prototype, Redis is sufficient

### 6. Authentication

**Decision**: API key-based authentication

**Implementation**:
- API key in `X-API-Key` header
- SHA-256 hashing (prototype)
- Tenant lookup on each request

**Production Upgrade**: JWT/OAuth2 with proper key hashing (bcrypt)

## Scalability Design

### Horizontal Scaling

- **API Layer**: Stateless, scale with load balancer
- **Workers**: Scale independently per worker type
- **Qdrant**: Cluster mode for 1M+ vectors
- **PostgreSQL**: Read replicas for search queries

### Performance Optimizations

1. **Batch Processing**: Process chunks in batches (100-500)
2. **Connection Pooling**: For PostgreSQL and Qdrant
3. **Caching**: Redis cache for frequent queries
4. **Parallel Workers**: Multiple workers per type

### Throughput Targets

- **50K docs/24h per tenant**: ~35 docs/min
- **1M total docs**: Distributed across 20+ tenants
- **Search latency**: <100ms with proper indexing

## Failure Handling

### Retry Logic

- **Max Retries**: 3 attempts
- **Backoff**: Exponential (2^retry_count seconds)
- **Idempotent Operations**: Safe to retry

### Checkpointing

- Intermediate results stored in object storage
- Parquet files for embeddings
- Job status tracked in PostgreSQL

### Dead Letter Queue

- Failed jobs after max retries logged
- Manual intervention required (can be automated)

### Health Checks

- Service health endpoints
- Worker monitoring
- Database connection checks

## Data Model

### PostgreSQL Schema

**tenants**
- `tenant_id` (UUID, PK)
- `name` (VARCHAR, UNIQUE)
- `api_key_hash` (VARCHAR, UNIQUE)
- `rate_limit` (INTEGER)
- `created_at` (TIMESTAMP)

**documents**
- `document_id` (UUID, PK)
- `tenant_id` (UUID, FK)
- `filename` (VARCHAR)
- `status` (VARCHAR)
- `file_path` (VARCHAR)
- `file_size` (BIGINT)
- `metadata` (JSONB)
- `created_at`, `updated_at` (TIMESTAMP)

**chunks**
- `chunk_id` (UUID, PK)
- `document_id` (UUID, FK)
- `tenant_id` (UUID, FK)
- `chunk_index` (INTEGER)
- `text` (TEXT)
- `embedding_path` (VARCHAR)
- `metadata` (JSONB)
- `created_at` (TIMESTAMP)

**jobs**
- `job_id` (UUID, PK)
- `tenant_id` (UUID, FK)
- `document_id` (UUID, FK)
- `job_type` (VARCHAR)
- `status` (VARCHAR)
- `error_message` (TEXT)
- `retry_count` (INTEGER)
- `max_retries` (INTEGER)
- `created_at`, `updated_at` (TIMESTAMP)

### Qdrant Collection

**Collection**: `document_chunks`

**Vector Size**: 1536 (OpenAI embeddings)

**Distance Metric**: Cosine

**Payload**:
- `tenant_id` (string)
- `document_id` (string)
- `chunk_id` (string)
- `text` (string)
- `filename` (string)
- `chunk_index` (integer)
- `metadata` (object)

## Trade-offs

### 1. Single Qdrant Collection vs. Per-Tenant Collections

**Chosen**: Single collection with tenant filtering

**Trade-off**:
- ✅ Simpler management
- ✅ Better resource utilization
- ❌ Potential query performance impact (mitigated by filtering)
- ❌ Less isolation (application-level only)

### 2. Synchronous Upload Response vs. True Async

**Chosen**: Fast response with job status endpoint

**Trade-off**:
- ✅ Fast feedback to user
- ✅ Simple implementation
- ❌ Requires status polling
- ❌ Not true async (acceptable for prototype)

### 3. Basic Auth vs. Enterprise SSO

**Chosen**: API key authentication

**Trade-off**:
- ✅ Simple for prototype
- ✅ Easy to implement
- ❌ Not enterprise-ready
- ❌ Manual key management

**Production**: Upgrade to JWT/OAuth2

### 4. Redis Queue vs. Kafka

**Chosen**: Redis with sorted sets

**Trade-off**:
- ✅ Simple and fast
- ✅ Sufficient for prototype
- ❌ Less durable than Kafka
- ❌ No built-in replication

**Production**: Consider Kafka for durability

## Production Readiness Gaps

1. **Monitoring**
   - Add Prometheus metrics
   - Set up Grafana dashboards
   - Implement structured logging

2. **Security**
   - HTTPS enforcement
   - Proper API key hashing (bcrypt)
   - Input validation
   - File size limits

3. **Backup**
   - Automated PostgreSQL backups
   - Qdrant snapshot management
   - Disaster recovery plan

4. **CI/CD**
   - Automated testing
   - Deployment pipelines
   - Load testing

5. **Observability**
   - Correlation IDs
   - Distributed tracing
   - Error tracking

## Future Enhancements

1. **Batch Embedding**: Process multiple chunks in single API call
2. **Streaming**: Real-time processing for large documents
3. **Advanced Chunking**: Semantic chunking with ML models
4. **Multi-Model Support**: Support for different embedding models
5. **Caching**: Cache embeddings for duplicate content
6. **Analytics**: Usage metrics and performance monitoring

## Conclusion

This design provides a solid foundation for a scalable RAG ingestion pipeline with clear paths for production deployment and scaling. The architecture balances simplicity with scalability, making it suitable for both prototype and production use.
