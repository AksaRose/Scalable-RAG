"""Shared data models."""
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field, HttpUrl


class DocumentStatus(str, Enum):
    """Document processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobType(str, Enum):
    """Job types."""
    EXTRACT = "extract"
    CHUNK = "chunk"
    EMBED = "embed"


class JobStatus(str, Enum):
    """Job processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Tenant(BaseModel):
    """Tenant model."""
    tenant_id: UUID
    name: str
    rate_limit: int
    created_at: datetime


class Document(BaseModel):
    """Document model."""
    document_id: UUID
    tenant_id: UUID
    filename: str
    status: DocumentStatus
    file_path: str
    file_size: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class Chunk(BaseModel):
    """Chunk model."""
    chunk_id: UUID
    document_id: UUID
    tenant_id: UUID
    chunk_index: int
    text: str
    embedding_path: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime


class Job(BaseModel):
    """Job model."""
    job_id: UUID
    tenant_id: UUID
    document_id: Optional[UUID] = None
    job_type: JobType
    status: JobStatus
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime
    updated_at: datetime


class UploadResponse(BaseModel):
    """Response model for file upload."""
    document_id: UUID
    filename: str
    status: str
    message: str


class BulkUploadResponse(BaseModel):
    """Response model for bulk upload."""
    total_files: int
    successful: int
    failed: int
    documents: list[UploadResponse]


class SearchRequest(BaseModel):
    """Search request model."""
    query: str = Field(..., min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=100)
    score_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class SearchResult(BaseModel):
    """Search result model."""
    chunk_id: UUID
    document_id: UUID
    tenant_id: UUID  # Added: Reference to source tenant
    filename: str
    text: str
    score: float
    metadata: Optional[Dict[str, Any]] = None


class SearchResponse(BaseModel):
    """Search response model."""
    results: list[SearchResult]
    total: int
    query: str


class StatusResponse(BaseModel):
    """Status response model."""
    document_id: UUID
    status: str
    progress: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ============== Webhook Support ==============

class WebhookConfig(BaseModel):
    """Webhook configuration for async notifications."""
    url: HttpUrl = Field(..., description="URL to receive webhook notifications")
    secret: Optional[str] = Field(None, description="Secret for HMAC signature verification")
    events: List[str] = Field(
        default=["completed", "failed"],
        description="Events to notify: completed, failed, processing"
    )


class UploadRequestWithWebhook(BaseModel):
    """Upload request with optional webhook."""
    webhook: Optional[WebhookConfig] = None


class WebhookPayload(BaseModel):
    """Payload sent to webhook URL."""
    event: str  # completed, failed, processing
    document_id: UUID
    tenant_id: UUID
    filename: str
    status: str
    timestamp: datetime
    error: Optional[str] = None
    chunks_count: Optional[int] = None


# ============== Metrics & Observability ==============

class SystemMetrics(BaseModel):
    """System-wide metrics."""
    total_documents: int
    total_chunks: int
    total_tenants: int
    documents_by_status: Dict[str, int]
    avg_processing_time_seconds: Optional[float] = None
    queue_depths: Dict[str, int]
    storage_used_bytes: Optional[int] = None


class TenantMetrics(BaseModel):
    """Per-tenant metrics."""
    tenant_id: UUID
    tenant_name: str
    document_count: int
    chunk_count: int
    storage_used_bytes: Optional[int] = None
    last_upload: Optional[datetime] = None
    rate_limit: int
    current_rate: int  # Requests in current window


# ============== Document Management ==============

class DocumentDeleteResponse(BaseModel):
    """Response for document deletion."""
    document_id: UUID
    deleted: bool
    message: str
    chunks_deleted: int = 0
    vectors_deleted: int = 0


class TenantQuota(BaseModel):
    """Tenant quota/limits."""
    tenant_id: UUID
    max_documents: Optional[int] = None  # None = unlimited
    max_storage_bytes: Optional[int] = None
    current_documents: int
    current_storage_bytes: int
    usage_percentage: float
