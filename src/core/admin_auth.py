"""
Pulse Platform — admin auth.

Parallel to src/core/auth.py::get_current_tenant, but for the single-operator
admin console rather than tenant API access. No DB lookup, no hashing — this
is one static secret (ADMIN_SECRET) compared with a constant-time comparison,
not a per-tenant credential. If this ever needs to support more than one
admin user, that's a real auth system (rows, roles, rotation) — not a bigger
version of this function.
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from src.core.config import settings


async def require_admin(authorization: str = Header(default="")) -> None:
    if not settings.admin_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin console not configured (ADMIN_SECRET unset)",
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )

    token = authorization.removeprefix("Bearer ").strip()

    if not secrets.compare_digest(token, settings.admin_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin secret",
        )
