"""Upload routes with rate limiting."""
import os
import uuid
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Header
from typing import List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import redis
from shared.config import config
from shared.models import UploadResponse, BulkUploadResponse
from shared.queue import QueueClient
from services.auth import AuthService
from services.storage import StorageService
import logging
import time

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])

# Redis client for rate limiting
_rate_limit_redis = redis.from_url(config.REDIS_URL, decode_responses=True)


def check_rate_limit(tenant_id: str, rate_limit: int) -> bool:
    """Check if tenant is within rate limit using sliding window.
    
    Args:
        tenant_id: Tenant ID
        rate_limit: Max requests per minute
        
    Returns:
        True if within limit, raises HTTPException if exceeded
    """
    key = f"rate_limit:{tenant_id}"
    current_time = int(time.time())
    window_start = current_time - 60  # 1 minute window
    
    # Remove old entries
    _rate_limit_redis.zremrangebyscore(key, 0, window_start)
    
    # Count requests in current window
    current_count = _rate_limit_redis.zcard(key)
    
    if current_count >= rate_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {rate_limit} requests per minute."
        )
    
    # Add current request
    _rate_limit_redis.zadd(key, {f"{current_time}:{uuid.uuid4()}": current_time})
    _rate_limit_redis.expire(key, 120)  # Expire after 2 minutes
    
    return True


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
    
    # Enforce rate limit
    check_rate_limit(tenant['tenant_id'], tenant.get('rate_limit', 100))
    
    return tenant


@router.post("/single", response_model=UploadResponse)
async def upload_single_file(
    file: UploadFile = File(...),
    tenant: dict = Depends(get_current_tenant)
):
    """Upload a single file for processing."""
    # Validate file extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(config.ALLOWED_EXTENSIONS)}"
        )
    
    # Read file content
    file_content = await file.read()
    file_size = len(file_content)
    
    # Validate file size
    if file_size > config.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds maximum of {config.MAX_FILE_SIZE} bytes"
        )
    
    # Generate document ID and file path
    document_id = uuid.uuid4()
    tenant_id = tenant['tenant_id']
    file_path = f"{tenant_id}/{document_id}/{file.filename}"
    
    conn = None
    try:
        # Upload to object storage
        logger.info(f"Uploading file to storage: {file_path}")
        storage_service = StorageService()
        storage_service.upload_file(file_content, file_path)
        logger.info(f"File uploaded to storage successfully")
        
        # Create document record in database
        conn = psycopg2.connect(config.DATABASE_URL)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO documents (document_id, tenant_id, filename, status, file_path, file_size)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING document_id, status
                """,
                (str(document_id), str(tenant_id), file.filename, "pending", file_path, file_size)
            )
            result = cur.fetchone()
            conn.commit()
        logger.info(f"Document record created in database")
        
        # Enqueue extraction job
        logger.info(f"Enqueueing extraction job for document: {document_id}")
        queue_client = QueueClient()
        queue_client.enqueue_job(
            job_type="extract",
            tenant_id=str(tenant_id),
            document_id=str(document_id),
            payload={"file_path": file_path, "filename": file.filename}
        )
        logger.info(f"Extraction job enqueued successfully")
        
        return UploadResponse(
            document_id=document_id,
            filename=file.filename,
            status="pending",
            message="File uploaded successfully and queued for processing"
        )
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Error uploading file: {e}\n{error_trace}")
        if conn:
            try:
                conn.close()
            except:
                pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error uploading file: {str(e)}"
        )


@router.post("/bulk", response_model=BulkUploadResponse)
async def upload_bulk_files(
    files: List[UploadFile] = File(...),
    tenant: dict = Depends(get_current_tenant)
):
    """Upload multiple files for processing."""
    if len(files) > 100:  # Limit bulk upload size
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 100 files allowed per bulk upload"
        )
    
    tenant_id = tenant['tenant_id']
    storage_service = StorageService()
    queue_client = QueueClient()
    conn = psycopg2.connect(config.DATABASE_URL)
    
    successful = 0
    failed = 0
    document_responses = []
    
    for file in files:
        try:
            # Validate file extension
            file_ext = os.path.splitext(file.filename)[1].lower()
            if file_ext not in config.ALLOWED_EXTENSIONS:
                failed += 1
                document_responses.append(
                    UploadResponse(
                        document_id=uuid.uuid4(),
                        filename=file.filename,
                        status="failed",
                        message=f"Invalid file type: {file_ext}"
                    )
                )
                continue
            
            # Read file content
            file_content = await file.read()
            file_size = len(file_content)
            
            # Validate file size
            if file_size > config.MAX_FILE_SIZE:
                failed += 1
                document_responses.append(
                    UploadResponse(
                        document_id=uuid.uuid4(),
                        filename=file.filename,
                        status="failed",
                        message=f"File size exceeds maximum"
                    )
                )
                continue
            
            # Generate document ID and file path
            document_id = uuid.uuid4()
            file_path = f"{tenant_id}/{document_id}/{file.filename}"
            
            # Upload to object storage
            storage_service.upload_file(file_content, file_path)
            
            # Create document record
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO documents (document_id, tenant_id, filename, status, file_path, file_size)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING document_id, status
                    """,
                    (str(document_id), str(tenant_id), file.filename, "pending", file_path, file_size)
                )
                conn.commit()
            
            # Enqueue extraction job
            queue_client.enqueue_job(
                job_type="extract",
                tenant_id=str(tenant_id),
                document_id=str(document_id),
                payload={"file_path": file_path, "filename": file.filename}
            )
            
            successful += 1
            document_responses.append(
                UploadResponse(
                    document_id=document_id,
                    filename=file.filename,
                    status="pending",
                    message="File uploaded successfully"
                )
            )
        except Exception as e:
            logger.error(f"Error processing file {file.filename}: {e}")
            failed += 1
            document_responses.append(
                UploadResponse(
                    document_id=uuid.uuid4(),
                    filename=file.filename,
                    status="failed",
                    message=f"Error: {str(e)}"
                )
            )
    
    conn.close()
    
    return BulkUploadResponse(
        total_files=len(files),
        successful=successful,
        failed=failed,
        documents=document_responses
    )
