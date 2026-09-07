"""
Pulse Platform — admin API key revocation.

Usage:
    python scripts/revoke_api_key.py <key_prefix>

Revokes the key matching the given prefix (as printed by create_tenant.py or
looked up via `select key_prefix from api_keys where tenant_id = ...`). To
issue a replacement, run create_tenant.py's key-minting logic again for the
same tenant (a rotate_api_key.py wrapper is a straightforward addition once
there's a second real use for it).
"""

from __future__ import annotations

import asyncio
import sys

import asyncpg

sys.path.insert(0, ".")

from src.core.config import settings


async def main(key_prefix: str) -> None:
    conn = await asyncpg.connect(settings.database_url)
    try:
        result = await conn.execute(
            "update api_keys set revoked_at = now() where key_prefix = $1 and revoked_at is null",
            key_prefix,
        )
        if result == "UPDATE 0":
            print(f"No active key found with prefix {key_prefix}")
        else:
            print(f"Revoked key {key_prefix}")
    finally:
        await conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/revoke_api_key.py <key_prefix>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
