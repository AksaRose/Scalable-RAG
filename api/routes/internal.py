"""Internal service authentication routes."""
import os
import hashlib
from fastapi import APIRouter, Depends, HTTPException, status, Header
from typing import Optional
from pydantic import BaseModel
from shared.config import config
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])

# Internal service token (should be set via environment variable in production)
INTERNAL_SERVICE_TOKEN = os.getenv("INTERNAL_SERVICE_TOKEN", "internal_service_secret_token")
INTERNAL_TOKEN_HASH = hashlib.sha256(INTERNAL_SERVICE_TOKEN.encode()).hexdigest()


class ServiceAuthResponse(BaseModel):
    """Response for service authentication."""
    authenticated: bool
    service_name: str
    permissions: list[str]


class HealthCheckResponse(BaseModel):
    """Internal health check response."""
    status: str
    database: str
    redis: str
    qdrant: str
    minio: str


def verify_internal_token(x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token")) -> bool:
    """Verify internal service token.
    
    Args:
        x_internal_token: Internal service token from header
        
    Returns:
        True if valid, raises HTTPException if invalid
    """
    if not x_internal_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Internal service token required"
        )
    
    token_hash = hashlib.sha256(x_internal_token.encode()).hexdigest()
    
    if token_hash != INTERNAL_TOKEN_HASH:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal service token"
        )
    
    return True


@router.get("/auth", response_model=ServiceAuthResponse)
async def authenticate_service(
    x_service_name: Optional[str] = Header(None, alias="X-Service-Name"),
    _: bool = Depends(verify_internal_token)
):
    """Authenticate an internal service.
    
    Headers:
        X-Internal-Token: Internal service authentication token
        X-Service-Name: Name of the calling service (optional)
    
    Returns:
        Authentication status and permissions
    """
    service_name = x_service_name or "unknown_service"
    logger.info(f"Internal service authenticated: {service_name}")
    
    return ServiceAuthResponse(
        authenticated=True,
        service_name=service_name,
        permissions=[
            "read:documents",
            "write:documents",
            "read:chunks",
            "write:chunks",
            "search:vectors",
            "admin:tenants"
        ]
    )


@router.get("/health", response_model=HealthCheckResponse)
async def internal_health_check(_: bool = Depends(verify_internal_token)):
    """Detailed health check for internal services.
    
    Returns:
        Health status of all dependent services
    """
    import psycopg2
    import redis
    from minio import Minio
    from qdrant_client import QdrantClient
    
    results = {
        "database": "unknown",
        "redis": "unknown",
        "minio": "unknown",
        "qdrant": "unknown"
    }
    
    # Check PostgreSQL
    try:
        conn = psycopg2.connect(config.DATABASE_URL)
        conn.close()
        results["database"] = "healthy"
    except Exception as e:
        results["database"] = f"unhealthy: {str(e)}"
    
    # Check Redis
    try:
        r = redis.from_url(config.REDIS_URL)
        r.ping()
        results["redis"] = "healthy"
    except Exception as e:
        results["redis"] = f"unhealthy: {str(e)}"
    
    # Check MinIO
    try:
        client = Minio(
            config.MINIO_ENDPOINT,
            access_key=config.MINIO_ACCESS_KEY,
            secret_key=config.MINIO_SECRET_KEY,
            secure=config.MINIO_SECURE
        )
        client.list_buckets()
        results["minio"] = "healthy"
    except Exception as e:
        results["minio"] = f"unhealthy: {str(e)}"
    
    # Check Qdrant
    try:
        client = QdrantClient(url=config.QDRANT_URL)
        client.get_collections()
        results["qdrant"] = "healthy"
    except Exception as e:
        results["qdrant"] = f"unhealthy: {str(e)}"
    
    all_healthy = all("healthy" == v for v in results.values())
    
    return HealthCheckResponse(
        status="healthy" if all_healthy else "degraded",
        **results
    )


@router.get("/tenants")
async def list_all_tenants(_: bool = Depends(verify_internal_token)):
    """List all tenants (admin endpoint for internal services).
    
    Returns:
        List of all tenants
    """
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    try:
        conn = psycopg2.connect(config.DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT tenant_id, name, rate_limit, created_at
                FROM tenants
                ORDER BY created_at DESC
            """)
            tenants = cur.fetchall()
        conn.close()
        
        return {
            "tenants": [dict(t) for t in tenants],
            "total": len(tenants)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching tenants: {str(e)}"
        )


class CreateTenantRequest(BaseModel):
    """Request to create a new tenant."""
    name: str
    rate_limit: int = 100


class CreateTenantResponse(BaseModel):
    """Response after creating a tenant."""
    tenant_id: str
    name: str
    api_key: str  # Plain text key - only shown once!
    rate_limit: int
    message: str


@router.post("/tenants", response_model=CreateTenantResponse)
async def create_tenant(
    request: CreateTenantRequest,
    _: bool = Depends(verify_internal_token)
):
    """Create a new tenant and generate their API key.
    
    IMPORTANT: The api_key is only returned once. Store it securely!
    
    Args:
        request: Tenant creation request with name and rate_limit
        
    Returns:
        Tenant details including the plain-text API key (shown only once)
    """
    import psycopg2
    from psycopg2.extras import RealDictCursor
    import secrets
    
    # Generate a secure API key
    api_key = f"{request.name}_{secrets.token_urlsafe(24)}"
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    try:
        conn = psycopg2.connect(config.DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                INSERT INTO tenants (name, api_key_hash, rate_limit)
                VALUES (%s, %s, %s)
                RETURNING tenant_id, name, rate_limit, created_at
            """, (request.name, api_key_hash, request.rate_limit))
            tenant = cur.fetchone()
            conn.commit()
        conn.close()
        
        logger.info(f"Created new tenant: {request.name}")
        
        return CreateTenantResponse(
            tenant_id=str(tenant["tenant_id"]),
            name=tenant["name"],
            api_key=api_key,  # Only time this is shown!
            rate_limit=tenant["rate_limit"],
            message="Tenant created successfully. Save the API key - it won't be shown again!"
        )
        
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant with name '{request.name}' already exists"
        )
    except Exception as e:
        logger.error(f"Error creating tenant: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating tenant: {str(e)}"
        )


@router.delete("/tenants/{tenant_name}")
async def delete_tenant(
    tenant_name: str,
    _: bool = Depends(verify_internal_token)
):
    """Delete a tenant and all their data.
    
    WARNING: This permanently deletes all tenant data!
    
    Args:
        tenant_name: Name of the tenant to delete
        
    Returns:
        Deletion confirmation
    """
    import psycopg2
    
    try:
        conn = psycopg2.connect(config.DATABASE_URL)
        with conn.cursor() as cur:
            # Delete tenant (cascades to documents, chunks, jobs)
            cur.execute("DELETE FROM tenants WHERE name = %s RETURNING tenant_id", (tenant_name,))
            result = cur.fetchone()
            
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Tenant '{tenant_name}' not found"
                )
            
            conn.commit()
        conn.close()
        
        logger.info(f"Deleted tenant: {tenant_name}")
        
        return {
            "message": f"Tenant '{tenant_name}' deleted successfully",
            "tenant_id": str(result[0])
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting tenant: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting tenant: {str(e)}"
        )


@router.get("/documents")
async def list_all_documents(
    tenant_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    _: bool = Depends(verify_internal_token)
):
    """List documents across all tenants (or filter by tenant).
    
    Internal services can access ANY tenant's documents.
    
    Args:
        tenant_id: Optional filter by tenant
        status: Optional filter by status (pending, processing, completed, failed)
        limit: Maximum results (default 100)
        
    Returns:
        List of documents
    """
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    try:
        conn = psycopg2.connect(config.DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = """
                SELECT d.document_id, d.tenant_id, t.name as tenant_name, 
                       d.filename, d.status, d.file_size, d.created_at
                FROM documents d
                JOIN tenants t ON d.tenant_id = t.tenant_id
                WHERE 1=1
            """
            params = []
            
            if tenant_id:
                query += " AND d.tenant_id = %s"
                params.append(tenant_id)
            if status:
                query += " AND d.status = %s"
                params.append(status)
            
            query += " ORDER BY d.created_at DESC LIMIT %s"
            params.append(limit)
            
            cur.execute(query, params)
            documents = cur.fetchall()
        conn.close()
        
        return {
            "documents": [dict(d) for d in documents],
            "total": len(documents)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching documents: {str(e)}"
        )


@router.get("/documents/{document_id}")
async def get_document_details(
    document_id: str,
    _: bool = Depends(verify_internal_token)
):
    """Get full document details including chunks (cross-tenant access).
    
    Args:
        document_id: Document UUID
        
    Returns:
        Document with all chunks
    """
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    try:
        conn = psycopg2.connect(config.DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get document
            cur.execute("""
                SELECT d.*, t.name as tenant_name
                FROM documents d
                JOIN tenants t ON d.tenant_id = t.tenant_id
                WHERE d.document_id = %s
            """, (document_id,))
            document = cur.fetchone()
            
            if not document:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found"
                )
            
            # Get chunks
            cur.execute("""
                SELECT chunk_id, chunk_index, text, embedding_path, created_at
                FROM chunks
                WHERE document_id = %s
                ORDER BY chunk_index
            """, (document_id,))
            chunks = cur.fetchall()
            
            # Get jobs
            cur.execute("""
                SELECT job_id, job_type, status, error_message, retry_count, created_at
                FROM jobs
                WHERE document_id = %s
                ORDER BY created_at
            """, (document_id,))
            jobs = cur.fetchall()
        
        conn.close()
        
        return {
            "document": dict(document),
            "chunks": [dict(c) for c in chunks],
            "jobs": [dict(j) for j in jobs]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching document: {str(e)}"
        )


@router.post("/search")
async def internal_search(
    query: str,
    tenant_id: Optional[str] = None,
    limit: int = 10,
    score_threshold: float = 0.3,
    _: bool = Depends(verify_internal_token)
):
    """Search across ALL tenants or specific tenant (internal only).
    
    Unlike the public /search endpoint, this can search across tenant boundaries.
    
    Args:
        query: Search query
        tenant_id: Optional - filter to specific tenant (None = all tenants)
        limit: Maximum results
        score_threshold: Minimum similarity score
        
    Returns:
        Search results from any/all tenants
    """
    from sentence_transformers import SentenceTransformer
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    
    try:
        # Load model and generate embedding
        model = SentenceTransformer(config.EMBEDDING_MODEL)
        query_vector = model.encode(query, convert_to_numpy=True).tolist()
        
        # Search Qdrant
        qdrant = QdrantClient(url=config.QDRANT_URL)
        
        # Build filter (optional tenant filter)
        search_filter = None
        if tenant_id:
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="tenant_id",
                        match=MatchValue(value=tenant_id)
                    )
                ]
            )
        
        results = qdrant.search(
            collection_name=config.QDRANT_COLLECTION_NAME,
            query_vector=query_vector,
            query_filter=search_filter,
            limit=limit,
            score_threshold=score_threshold
        )
        
        return {
            "results": [
                {
                    "chunk_id": r.id,
                    "score": r.score,
                    "tenant_id": r.payload.get("tenant_id"),
                    "document_id": r.payload.get("document_id"),
                    "filename": r.payload.get("filename"),
                    "text": r.payload.get("text"),
                    "chunk_index": r.payload.get("chunk_index")
                }
                for r in results
            ],
            "total": len(results),
            "query": query,
            "filtered_by_tenant": tenant_id
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching: {str(e)}"
        )


@router.get("/stats")
async def get_system_stats(_: bool = Depends(verify_internal_token)):
    """Get system statistics (for monitoring/observability).
    
    Returns comprehensive system statistics including:
    - Document counts by status
    - Job counts by status (including failed jobs)
    - Queue depths for each worker type
    - Vector store statistics
    - Failed jobs details for troubleshooting
    """
    import psycopg2
    import redis
    from psycopg2.extras import RealDictCursor
    from qdrant_client import QdrantClient
    from shared.queue import QueueClient
    
    stats = {
        "total_documents": 0,
        "total_tenants": 0,
        "documents_by_status": {},
        "jobs_by_status": {},
        "queue_depths": {},
        "vectors": 0,
        "chunks": 0,
        "failed_jobs": [],
        "alerts": []
    }
    
    try:
        conn = psycopg2.connect(config.DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Document stats
            cur.execute("SELECT COUNT(*) as total FROM documents")
            stats["total_documents"] = cur.fetchone()["total"]
            
            cur.execute("SELECT COUNT(*) as total, status FROM documents GROUP BY status")
            doc_stats = cur.fetchall()
            stats["documents_by_status"] = {row["status"]: row["total"] for row in doc_stats}
            
            # Chunk stats
            cur.execute("SELECT COUNT(*) as total FROM chunks")
            stats["chunks"] = cur.fetchone()["total"]
            
            # Job stats
            cur.execute("SELECT COUNT(*) as total, status FROM jobs GROUP BY status")
            job_stats = cur.fetchall()
            stats["jobs_by_status"] = {row["status"]: row["total"] for row in job_stats}
            
            # Failed jobs details (last 10)
            cur.execute("""
                SELECT job_id, tenant_id, document_id, job_type, error_message, 
                       retry_count, created_at, updated_at
                FROM jobs 
                WHERE status = 'failed'
                ORDER BY updated_at DESC
                LIMIT 10
            """)
            failed_jobs = cur.fetchall()
            stats["failed_jobs"] = [dict(j) for j in failed_jobs]
            
            # Tenant stats
            cur.execute("SELECT COUNT(*) as total FROM tenants")
            stats["total_tenants"] = cur.fetchone()["total"]
        
        conn.close()
        
        # Queue depths (observability for processing backlog)
        try:
            queue_client = QueueClient()
            stats["queue_depths"] = {
                "extract": queue_client.get_queue_size("extract"),
                "chunk": queue_client.get_queue_size("chunk"),
                "embed": queue_client.get_queue_size("embed")
            }
            
            # Alert if queues are backing up
            for queue_type, depth in stats["queue_depths"].items():
                if depth > 1000:
                    stats["alerts"].append(f"High queue depth for {queue_type}: {depth}")
        except Exception as e:
            stats["queue_depths"] = {"error": str(e)}
        
        # Qdrant stats
        try:
            qdrant = QdrantClient(url=config.QDRANT_URL)
            collection_info = qdrant.get_collection(config.QDRANT_COLLECTION_NAME)
            stats["vectors"] = collection_info.points_count
        except:
            stats["vectors"] = "unavailable"
        
        # Generate alerts
        if stats.get("jobs_by_status", {}).get("failed", 0) > 0:
            stats["alerts"].append(f"There are {stats['jobs_by_status']['failed']} failed jobs")
        
        if stats.get("documents_by_status", {}).get("failed", 0) > 0:
            stats["alerts"].append(f"There are {stats['documents_by_status']['failed']} failed documents")
        
        return stats
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching stats: {str(e)}"
        )
