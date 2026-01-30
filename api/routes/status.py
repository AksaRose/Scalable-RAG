"""Status routes."""
from fastapi import APIRouter, Depends, HTTPException, status, Header
from typing import Optional
from uuid import UUID
import psycopg2
from psycopg2.extras import RealDictCursor
from shared.models import StatusResponse
from shared.config import config
from services.auth import AuthService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/status", tags=["status"])

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


@router.get("/{document_id}", response_model=StatusResponse)
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
