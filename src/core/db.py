"""
Pulse Platform — Postgres connection pool.

One asyncpg pool for the process, created on FastAPI startup and closed on
shutdown. Every query goes through this — no per-request connections.
"""

from __future__ import annotations

import asyncpg

from src.core.config import settings

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=10)


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call init_pool() on startup first")
    return _pool
