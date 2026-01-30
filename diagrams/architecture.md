# System Architecture Diagram

## High-Level Architecture

```mermaid
graph TB
    Client[Client Applications] -->|HTTP/HTTPS| API[FastAPI Service]
    API -->|Authenticate| Auth[Auth Service]
    API -->|Queue Jobs| Queue[Redis Queue]
    API -->|Store Metadata| Postgres[(PostgreSQL)]
    API -->|Query Vectors| Qdrant[(Qdrant)]
    
    Queue -->|Process| TextWorker[Text Extraction Workers]
    Queue -->|Process| ChunkWorker[Chunking Workers]
    Queue -->|Process| EmbedWorker[Embedding Workers]
    
    TextWorker -->|Store| Storage[S3/MinIO]
    ChunkWorker -->|Read/Write| Storage
    EmbedWorker -->|Read/Write| Storage
    EmbedWorker -->|Bulk Insert| Qdrant
    
    TextWorker -->|Update Status| Postgres
    ChunkWorker -->|Update Status| Postgres
    EmbedWorker -->|Update Status| Postgres
```

## Processing Pipeline Flow

```mermaid
sequenceDiagram
    participant Client
    participant API
    participant Queue
    participant Storage
    participant TextWorker
    participant ChunkWorker
    participant EmbedWorker
    participant Qdrant
    participant Postgres

    Client->>API: Upload Document
    API->>Storage: Store File
    API->>Postgres: Create Document Record
    API->>Queue: Enqueue Extract Job
    API->>Client: Return Document ID

    Queue->>TextWorker: Dequeue Extract Job
    TextWorker->>Storage: Download File
    TextWorker->>Storage: Store Extracted Text
    TextWorker->>Postgres: Update Status
    TextWorker->>Queue: Enqueue Chunk Job

    Queue->>ChunkWorker: Dequeue Chunk Job
    ChunkWorker->>Storage: Download Text
    ChunkWorker->>Postgres: Store Chunks
    ChunkWorker->>Storage: Store Chunk Files
    ChunkWorker->>Queue: Enqueue Embed Jobs

    Queue->>EmbedWorker: Dequeue Embed Job
    EmbedWorker->>Storage: Download Chunk
    EmbedWorker->>EmbedWorker: Generate Embedding (local model)
    EmbedWorker->>Storage: Store Parquet
    EmbedWorker->>Qdrant: Upsert Vector
    EmbedWorker->>Postgres: Update Status
```

## Multi-Tenancy Architecture

```mermaid
graph LR
    Tenant1[Tenant 1] -->|API Key 1| API
    Tenant2[Tenant 2] -->|API Key 2| API
    Tenant3[Tenant 3] -->|API Key 3| API
    
    API -->|Filter by tenant_id| Postgres[(PostgreSQL)]
    API -->|Filter by tenant_id| Qdrant[(Qdrant)]
    
    Queue -->|Per-tenant queues| Queue1[Queue: tenant1:extract]
    Queue -->|Per-tenant queues| Queue2[Queue: tenant2:extract]
    Queue -->|Per-tenant queues| Queue3[Queue: tenant3:extract]
    
    Queue1 --> Worker[Workers]
    Queue2 --> Worker
    Queue3 --> Worker
```

## Component Details

### API Service
- FastAPI application
- Handles authentication
- Manages file uploads
- Provides search endpoints
- Status tracking

### Workers
- **Text Extractor**: PDF/TXT extraction using pypdf
- **Chunker**: Overlapping semantic chunking with sentence-aware breaking
- **Embedder**: Local embedding generation using sentence-transformers (BAAI/bge-small-en-v1.5)

### Storage
- **PostgreSQL**: Metadata and job tracking
- **Qdrant**: Vector database (384 dimensions with BAAI/bge-small-en-v1.5)
- **MinIO**: Object storage for files and intermediate data (Parquet)
- **Redis**: Job queue with sorted sets for per-tenant fairness
