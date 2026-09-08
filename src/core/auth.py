"""
Pulse Platform — tenant API key auth (FastAPI request dependency).

Key generation/hashing lives in api_keys.py (no FastAPI dependency, so admin
scripts don't need the web framework installed). This module adds the
request-scoped lookup on top: verify the Bearer token, resolve the tenant.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException, status

from src.core.api_keys import hash_api_key
from src.core.db import get_pool


@dataclass
class Tenant:
    id: str
    name: str
    plan: str


async def get_current_tenant(
    authorization: str = Header(default=""),
) -> Tenant:
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )

    api_key = authorization.removeprefix("Bearer ").strip()
    key_hash = hash_api_key(api_key)

    pool = get_pool()
    row = await pool.fetchrow(
        """
        select t.id, t.name, t.plan
        from api_keys k
        join tenants t on t.id = k.tenant_id
        where k.key_hash = $1 and k.revoked_at is null
        """,
        key_hash,
    )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
        )

    return Tenant(id=str(row["id"]), name=row["name"], plan=row["plan"])
