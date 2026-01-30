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

**Decision**: Open-source embeddings with batch processing and intermediate storage

**Model**: `BAAI/bge-small-en-v1.5` (384 dimensions) via sentence-transformers
- No API costs
- Self-hosted for privacy
- Configurable via `EMBEDDING_MODEL` environment variable

**Alternative Models Supported**:
- `all-MiniLM-L6-v2`
- `all-mpnet-base-v2`
- `BAAI/bge-base-en-v1.5`

**Batch Processing**: 100-500 chunks per batch

**Intermediate Storage**: Parquet files before bulk insert
- **Benefits**: Fault tolerance, retry capability, data recovery

### 4. Fairness Mechanism

**Decision**: Per-tenant queues with round-robin scheduling ✅ **Implemented**

**Implementation**:
- Separate Redis sorted sets per tenant and job type (`queue:{tenant_id}:{job_type}`)
- Workers dequeue in true round-robin across tenant queues (tracks last served tenant)
- Priority-based processing within tenant queues (higher score = higher priority)

**Rate Limiting**: Sliding window algorithm (configurable per tenant) ✅ **Implemented**
- Uses Redis sorted sets to track requests per tenant
- 1-minute sliding window with configurable limit per tenant
- Returns HTTP 429 when limit exceeded

**Bulk Upload Handling**: 
- Maximum 100 files per bulk upload
- Each file enqueued separately for parallel processing

### 5. Queue System

**Decision**: Redis with sorted sets for priority queues

**Rationale**:
- Simple and fast
- Supports priority-based processing
- Easy to implement per-tenant queues

**Alternative Considered**: Kafka
- **Rejected** because: Overkill for prototype, Redis is sufficient

### 6. Authentication

**Decision**: Dual authentication system (Tenant + Internal Service)

#### Tenant Authentication (External Customers)
- **Header**: `X-API-Key`
- **Method**: SHA-256 hashing (prototype)
- **Flow**: API key → hash → lookup in `tenants` table
- **Scope**: Upload, Search, Status endpoints
- **Data Access**: **Own tenant data only** (strict isolation)

#### Internal Service Authentication (System Components)
- **Header**: `X-Internal-Token`
- **Method**: SHA-256 hashing
- **Flow**: Service token → hash → compare with env variable
- **Scope**: Admin endpoints (`/internal/*`)
- **Data Access**: **Cross-tenant access** (elevated privileges)

#### Why Internal Services Have Cross-Tenant Access

**Rationale**: Internal services require elevated access for legitimate system operations:

1. **Worker Services** (text_worker, chunk_worker, embed_worker)
   - Must process documents from ALL tenants
   - Cannot be scoped to single tenant

2. **Admin/Monitoring Tools**
   - Need system-wide statistics and health checks
   - Must view documents across tenants for debugging

3. **Analytics & Reporting**
   - Aggregate metrics across the platform
   - Usage tracking per tenant

**Security Model**:
```
┌─────────────────────────────────────────────────────────────┐
│                    ACCESS CONTROL MODEL                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  TENANT API (X-API-Key)         INTERNAL API (X-Internal)   │
│  ─────────────────────          ─────────────────────────   │
│  • Own documents only           • ALL documents             │
│  • Own search results           • Cross-tenant search       │
│  • Upload/Status/Search         • Admin/Stats/Health        │
│  • Strict isolation ✓           • Elevated privileges ✓     │
│                                                             │
│  Use case: Customer apps        Use case: System services   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Alternative Considered**: Tenant-scoped internal tokens
- **Rejected** because: Workers need to process jobs from any tenant's queue

#### API Endpoints

**Tenant Endpoints** (require `X-API-Key`):
- `POST /upload/single` - Upload single file
- `POST /upload/bulk` - Upload multiple files
- `GET /status/{id}` - Check processing status
- `POST /search` - Search own documents

**Internal Endpoints** (require `X-Internal-Token`):
- `GET /internal/auth` - Verify service authentication
- `GET /internal/health` - Detailed health check
- `GET /internal/stats` - System-wide statistics
- `GET /internal/tenants` - List all tenants
- `POST /internal/tenants` - Create new tenant
- `DELETE /internal/tenants/{name}` - Delete tenant
- `GET /internal/documents` - List documents (cross-tenant)
- `GET /internal/documents/{id}` - Document details (cross-tenant)
- `POST /internal/search` - Search (cross-tenant)

**Production Upgrades**:
1. Replace SHA-256 with bcrypt for API key hashing
2. Add JWT tokens for session management
3. Implement OAuth2 for enterprise SSO
4. Add API key rotation mechanism
5. ~~Add rate limiting enforcement~~ ✅ (implemented using Redis sliding window)
6. Add audit logging for authentication events
7. Add role-based access control (RBAC) for internal services
8. Implement service mesh (Istio) for mTLS between services

## Scalability Design

### Target Metrics

| Metric | Target | How Achieved |
|--------|--------|--------------|
| **Total documents** | 1,000,000+ | Qdrant + PostgreSQL sharding |
| **Documents/tenant** | 50,000 | Tenant filtering + indexes |
| **Ingestion throughput** | 50K/24h | Horizontal worker scaling |
| **Search latency** | <100ms | Payload index on `tenant_id` |

### Horizontal Scaling Strategy

#### API Layer
- **Stateless design**: No session state, any instance can handle any request
- **Load balancing**: Deploy behind nginx/ALB with health checks
- **Scale trigger**: CPU > 70% or response time > 200ms
- **Target**: 10+ instances for production

#### Worker Scaling
- **Independent scaling**: Each worker type scales separately
- **Scaling formula**: 
  - Text workers: 1 per 1000 docs/hour
  - Chunk workers: 1 per 2000 docs/hour  
  - Embed workers: 1 per 500 docs/hour (CPU-intensive)
- **For 50K docs/24h**: ~3 text, ~2 chunk, ~5 embed workers

#### Database Scaling (PostgreSQL)
- **Current**: Single instance (prototype)
- **Production path**:
  1. Read replicas for status/search queries
  2. Connection pooling (PgBouncer)
  3. Table partitioning by `tenant_id` for 100+ tenants
  4. Consider Citus for horizontal sharding at 10M+ rows

#### Vector Store Scaling (Qdrant)
- **Current**: Single node with payload index on `tenant_id`
- **Production path**:
  1. Enable sharding (automatic distribution)
  2. Cluster mode with 3+ nodes for HA
  3. HNSW parameters: `m=16, ef_construct=100` for 1M+ vectors
  4. Separate collections per large tenant (>100K docs) if needed

### Performance Optimizations

1. **Payload Indexing**: Created `tenant_id` index in Qdrant for O(1) filtering
2. **Batch Processing**: Embedding batch size = 100 chunks
3. **Connection Pooling**: Recommended for PostgreSQL/Qdrant
4. **Caching**: Redis for frequent queries (future)
5. **Parallel Workers**: Multiple workers per type

### Throughput Calculation

```
Target: 50,000 documents in 24 hours = 2,083 docs/hour = 35 docs/min

Per document processing time (estimated):
- Text extraction: 2-5 seconds
- Chunking: 1-2 seconds  
- Embedding (per chunk): 0.1 seconds × avg 10 chunks = 1 second
- Total: ~5-8 seconds/document

With 5 embed workers: 5 × 60/8 = ~37 docs/min ✓
```

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

**Vector Size**: 384 (BAAI/bge-small-en-v1.5 embeddings)

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

## Implemented Features (Beyond Basic Requirements)

### Observability
- **Correlation IDs**: Every request gets a unique correlation ID (`X-Correlation-ID` header)
- **Response Time**: Response includes `X-Response-Time` header
- **Structured Logging**: All logs include correlation ID for request tracing

### Document Management
- **Document Deletion**: `DELETE /documents/{id}` - Removes document, chunks, vectors, and files
- **Tenant Metrics**: `GET /metrics/me` - Usage stats for authenticated tenant

### Rate Limiting
- **Sliding Window**: Redis-based rate limiting with configurable limits per tenant
- **HTTP 429**: Returns "Too Many Requests" when limit exceeded

## Future Enhancements

1. **Webhook Notifications**: Notify on document processing completion (models defined)
2. **Batch Embedding**: Process multiple chunks in single API call
3. **Streaming**: Real-time processing for large documents
4. **Advanced Chunking**: Semantic chunking with ML models
5. **Multi-Model Support**: Support for different embedding models
6. **Caching**: Cache embeddings for duplicate content
7. **Prometheus Metrics**: Export metrics for monitoring
8. **Tenant Quotas**: Storage and document limits per tenant

## AWS Deployment (Terraform)

Terraform scripts are provided in the `terraform/` directory for AWS deployment:

```
terraform/
├── main.tf              # Main configuration
├── variables.tf         # Input variables  
├── outputs.tf           # Output values
├── terraform.tfvars.example
└── modules/
    ├── vpc/            # VPC, subnets, NAT gateway
    ├── ecs/            # ECS Fargate (API + workers)
    ├── rds/            # PostgreSQL on RDS
    ├── elasticache/    # Redis on ElastiCache
    ├── s3/             # Document storage
    ├── qdrant/         # Qdrant on EC2
    └── alb/            # Application Load Balancer
```

### AWS Services Used

| Local Service | AWS Equivalent |
|---------------|----------------|
| Docker Compose | ECS Fargate |
| PostgreSQL | RDS PostgreSQL |
| Redis | ElastiCache Redis |
| MinIO | S3 |
| Qdrant | EC2 with Docker |
| - | ALB (load balancer) |
| - | ECR (container registry) |
| - | CloudWatch (logging) |
| - | Secrets Manager |

### Quick Deploy

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
terraform init
terraform apply
```

### Estimated Monthly Cost (Development)

~$187/month for minimal configuration. See `terraform/README.md` for details.

## Conclusion

This design provides a solid foundation for a scalable RAG ingestion pipeline with clear paths for production deployment and scaling. The architecture balances simplicity with scalability, making it suitable for both prototype and production use.
