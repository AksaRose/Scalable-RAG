"""Document models for API."""
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel


class DocumentCreate(BaseModel):
    """Document creation model."""
    filename: str
    file_size: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class DocumentResponse(BaseModel):
    """Document response model."""
    document_id: UUID
    tenant_id: UUID
    filename: str
    status: str
    file_path: str
    file_size: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
