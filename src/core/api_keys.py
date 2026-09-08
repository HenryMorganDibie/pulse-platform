"""
Pulse Platform — API key generation and hashing.

Split out from auth.py deliberately: this module has no FastAPI dependency,
so scripts/create_tenant.py and scripts/revoke_api_key.py (which only mint or
revoke keys) don't need the web framework installed to run. auth.py imports
from here and adds the FastAPI-specific request-auth dependency on top.
"""

from __future__ import annotations

import hashlib
import secrets

KEY_PREFIX_LEN = 12  # "pk_live_" + 4 chars — enough to distinguish keys in a list


def generate_api_key() -> tuple[str, str]:
    """Returns (full_key, key_prefix). Only the caller sees full_key."""
    full_key = f"pk_live_{secrets.token_urlsafe(24)}"
    return full_key, full_key[:KEY_PREFIX_LEN]


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
