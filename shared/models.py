"""Shared data models."""
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field


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
