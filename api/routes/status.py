"""Status and document management routes."""
from fastapi import APIRouter, Depends, HTTPException, status, Header
from typing import Optional
from uuid import UUID
import psycopg2
from psycopg2.extras import RealDictCursor
from shared.models import StatusResponse, DocumentDeleteResponse, TenantMetrics
from shared.config import config
from services.auth import AuthService
from services.qdrant_client import QdrantService
from services.storage import StorageService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["status"])

# Dependency for getting current tenant
def get_current_tenant(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> dict:
    """Get current tenant from API key."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required"
        )
    
    auth_service = AuthService()
    tenant = auth_service.authenticate(x_api_key)
    auth_service.close()
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    return tenant


@router.get("/status/{document_id}", response_model=StatusResponse)
async def get_document_status(
    document_id: UUID,
    tenant: dict = Depends(get_current_tenant)
):
    """Get the processing status of a document."""
    try:
        conn = psycopg2.connect(config.DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get document status
            cur.execute(
                """
                SELECT document_id, status, metadata
                FROM documents
                WHERE document_id = %s AND tenant_id = %s
                """,
                (str(document_id), str(tenant['tenant_id']))
            )
            doc_result = cur.fetchone()
            
            if not doc_result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found"
                )
            
            # Get job statuses for this document
            cur.execute(
                """
                SELECT job_type, status, error_message, retry_count
                FROM jobs
                WHERE document_id = %s
                ORDER BY created_at
                """,
                (str(document_id),)
            )
            jobs = cur.fetchall()
            
            # Build progress information
            progress = {
                "extract": None,
                "chunk": None,
                "embed": None
            }
            
            for job in jobs:
                job_type = job['job_type']
                progress[job_type] = {
                    "status": job['status'],
                    "error": job['error_message'],
                    "retry_count": job['retry_count']
                }
            
            return StatusResponse(
                document_id=document_id,
                status=doc_result['status'],
                progress=progress,
                error=None
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting status: {str(e)}"
        )


@router.delete("/documents/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: UUID,
    tenant: dict = Depends(get_current_tenant)
):
    """Delete a document and all associated data (chunks, vectors, files)."""
    conn = None
    chunks_deleted = 0
    vectors_deleted = 0
    
    try:
        conn = psycopg2.connect(config.DATABASE_URL)
        tenant_id = str(tenant['tenant_id'])
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Verify document exists and belongs to tenant
            cur.execute(
                """
                SELECT document_id, file_path FROM documents
                WHERE document_id = %s AND tenant_id = %s
                """,
                (str(document_id), tenant_id)
            )
            doc = cur.fetchone()
            
            if not doc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Document not found"
                )
            
            # Get chunk IDs for vector deletion
            cur.execute(
                "SELECT chunk_id FROM chunks WHERE document_id = %s",
                (str(document_id),)
            )
            chunk_ids = [row['chunk_id'] for row in cur.fetchall()]
            chunks_deleted = len(chunk_ids)
            
            # Delete from Qdrant
            if chunk_ids:
                try:
                    qdrant = QdrantService()
                    qdrant.delete_points(chunk_ids, tenant_id)
                    vectors_deleted = len(chunk_ids)
                except Exception as e:
                    logger.warning(f"Error deleting vectors: {e}")
            
            # Delete from object storage
            try:
                storage = StorageService()
                storage.delete_prefix(f"{tenant_id}/{document_id}/")
            except Exception as e:
                logger.warning(f"Error deleting files: {e}")
            
            # Delete from database (cascade: jobs, chunks)
            cur.execute("DELETE FROM jobs WHERE document_id = %s", (str(document_id),))
            cur.execute("DELETE FROM chunks WHERE document_id = %s", (str(document_id),))
            cur.execute("DELETE FROM documents WHERE document_id = %s", (str(document_id),))
            conn.commit()
        
        return DocumentDeleteResponse(
            document_id=document_id,
            deleted=True,
            message="Document and all associated data deleted successfully",
            chunks_deleted=chunks_deleted,
            vectors_deleted=vectors_deleted
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        if conn:
            conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting document: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@router.get("/metrics/me", response_model=TenantMetrics)
async def get_tenant_metrics(
    tenant: dict = Depends(get_current_tenant)
):
    """Get metrics for the authenticated tenant."""
    try:
        conn = psycopg2.connect(config.DATABASE_URL)
        tenant_id = str(tenant['tenant_id'])
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get document count
            cur.execute(
                "SELECT COUNT(*) as count FROM documents WHERE tenant_id = %s",
                (tenant_id,)
            )
            doc_count = cur.fetchone()['count']
            
            # Get chunk count
            cur.execute(
                "SELECT COUNT(*) as count FROM chunks WHERE tenant_id = %s",
                (tenant_id,)
            )
            chunk_count = cur.fetchone()['count']
            
            # Get total storage used
            cur.execute(
                "SELECT COALESCE(SUM(file_size), 0) as total FROM documents WHERE tenant_id = %s",
                (tenant_id,)
            )
            storage_used = cur.fetchone()['total']
            
            # Get last upload time
            cur.execute(
                "SELECT MAX(created_at) as last_upload FROM documents WHERE tenant_id = %s",
                (tenant_id,)
            )
            last_upload = cur.fetchone()['last_upload']
        
        conn.close()
        
        # Get current rate (requests in last minute)
        import redis
        redis_client = redis.from_url(config.REDIS_URL, decode_responses=True)
        rate_key = f"rate_limit:{tenant_id}"
        current_rate = redis_client.zcard(rate_key)
        
        return TenantMetrics(
            tenant_id=tenant['tenant_id'],
            tenant_name=tenant['name'],
            document_count=doc_count,
            chunk_count=chunk_count,
            storage_used_bytes=storage_used,
            last_upload=last_upload,
            rate_limit=tenant.get('rate_limit', 100),
            current_rate=current_rate
        )
        
    except Exception as e:
        logger.error(f"Error getting tenant metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting metrics: {str(e)}"
        )
