"""
Pulse Platform — tenant API key auth.

Keys are generated as `pk_live_<32 random url-safe chars>`, shown to the tenant
exactly once at creation (via scripts/create_tenant.py — see that file for why
there is no public tenant-registration endpoint). Only a SHA-256 hash is
stored, so a lookup is a plain indexed equality query (unlike bcrypt, which is
deliberately non-indexable and meant for username-scoped password checks, not
secret-scoped API key lookups).

Keys live in their own `api_keys` table (not a column on `tenants`) so a
compromised key can be revoked — `revoked_at` set — without touching the
tenant row, and so a tenant can hold more than one active key later without a
schema change.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from fastapi import Header, HTTPException, status

from src.core.db import get_pool

KEY_PREFIX_LEN = 12  # "pk_live_" + 4 chars — enough to distinguish keys in a list


def generate_api_key() -> tuple[str, str]:
    """Returns (full_key, key_prefix). Only the caller sees full_key."""
    full_key = f"pk_live_{secrets.token_urlsafe(24)}"
    return full_key, full_key[:KEY_PREFIX_LEN]


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


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
