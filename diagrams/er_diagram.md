# Entity Relationship Diagram

## PostgreSQL Schema

```mermaid
erDiagram
    tenants ||--o{ documents : "has"
    tenants ||--o{ chunks : "has"
    tenants ||--o{ jobs : "has"
    documents ||--o{ chunks : "contains"
    documents ||--o{ jobs : "has"

    tenants {
        uuid tenant_id PK
        varchar name UK
        varchar api_key_hash UK
        integer rate_limit
        timestamp created_at
    }

    documents {
        uuid document_id PK
        uuid tenant_id FK
        varchar filename
        varchar status
        varchar file_path
        bigint file_size
        jsonb metadata
        timestamp created_at
        timestamp updated_at
    }

    chunks {
        uuid chunk_id PK
        uuid document_id FK
        uuid tenant_id FK
        integer chunk_index
        text text
        varchar embedding_path
        jsonb metadata
        timestamp created_at
    }

    jobs {
        uuid job_id PK
        uuid tenant_id FK
        uuid document_id FK
        varchar job_type
        varchar status
        text error_message
        integer retry_count
        integer max_retries
        timestamp created_at
        timestamp updated_at
    }
```

## Qdrant Collection Structure

```mermaid
graph TB
    Collection[document_chunks Collection]
    
    Collection --> Vector[Vector: 1536 dimensions]
    Collection --> Payload[Payload Metadata]
    
    Payload --> TenantID[tenant_id: string]
    Payload --> DocID[document_id: string]
    Payload --> ChunkID[chunk_id: string]
    Payload --> Text[text: string]
    Payload --> Filename[filename: string]
    Payload --> ChunkIndex[chunk_index: integer]
    Payload --> Metadata[metadata: object]
```

## Data Flow Relationships

```mermaid
graph LR
    Upload[File Upload] --> Doc[Document Record]
    Doc --> ExtractJob[Extract Job]
    ExtractJob --> Text[Extracted Text]
    Text --> ChunkJob[Chunk Job]
    ChunkJob --> Chunks[Chunk Records]
    Chunks --> EmbedJob[Embed Job]
    EmbedJob --> Embedding[Embedding Vector]
    Embedding --> QdrantPoint[Qdrant Point]
```

## Indexes

### PostgreSQL Indexes
- `idx_documents_tenant_id`: On documents(tenant_id)
- `idx_documents_status`: On documents(status)
- `idx_chunks_document_id`: On chunks(document_id)
- `idx_chunks_tenant_id`: On chunks(tenant_id)
- `idx_jobs_tenant_id`: On jobs(tenant_id)
- `idx_jobs_document_id`: On jobs(document_id)
- `idx_jobs_status`: On jobs(status)
- `idx_jobs_type`: On jobs(job_type)

### Qdrant Indexes
- HNSW index on vectors (automatic)
- Payload index on tenant_id (for filtering)
