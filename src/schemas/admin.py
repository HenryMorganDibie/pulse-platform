"""Pulse Platform — admin console request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class TenantCreateRequest(BaseModel):
    name: str


class TenantCreateResponse(BaseModel):
    tenant_id: str
    name: str
    api_key: str  # shown exactly once — never retrievable again after this response
    key_prefix: str


class TenantSummary(BaseModel):
    tenant_id: str
    name: str
    plan: str
    created_at: datetime
    active_key_count: int


class TenantListResponse(BaseModel):
    tenants: List[TenantSummary]


class KeySummary(BaseModel):
    key_prefix: str
    created_at: datetime
    revoked_at: Optional[datetime] = None


class KeyListResponse(BaseModel):
    keys: List[KeySummary]


class MintKeyResponse(BaseModel):
    api_key: str  # shown exactly once
    key_prefix: str


class RevokeKeyResponse(BaseModel):
    status: str
