"""Tenant models for API."""
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class TenantResponse(BaseModel):
    """Tenant response model."""
    tenant_id: UUID
    name: str
    rate_limit: int
    created_at: datetime
