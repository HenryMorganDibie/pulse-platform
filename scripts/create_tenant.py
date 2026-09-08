"""
Pulse Platform — admin tenant provisioning.

There is deliberately no public POST /tenants endpoint. Onboarding a new
customer is a low-frequency, trust-sensitive action (it mints a credential
with full access to that tenant's data) — it belongs behind operator access
to the database, not behind an unauthenticated or self-serve HTTP route.

Usage:
    python scripts/create_tenant.py "Acme Corp"

Prints the raw API key exactly once. It is not recoverable afterwards —
only its hash and prefix are stored. If it's lost, revoke it and mint a new
one (see revoke_api_key.py).
"""

from __future__ import annotations

import asyncio
import sys

import asyncpg

sys.path.insert(0, ".")

from src.core.api_keys import generate_api_key, hash_api_key
from src.core.config import settings


async def main(tenant_name: str) -> None:
    conn = await asyncpg.connect(settings.database_url)
    try:
        tenant_id = await conn.fetchval(
            "insert into tenants (name) values ($1) returning id",
            tenant_name,
        )

        full_key, prefix = generate_api_key()
        await conn.execute(
            "insert into api_keys (tenant_id, key_hash, key_prefix) values ($1, $2, $3)",
            tenant_id,
            hash_api_key(full_key),
            prefix,
        )

        print(f"Tenant created: {tenant_name} ({tenant_id})")
        print(f"API key (shown once — store it now):\n{full_key}")
    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/create_tenant.py \"Tenant Name\"")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
