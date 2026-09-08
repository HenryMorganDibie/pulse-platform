"""
Pulse Platform — Postgres connection pool.

One asyncpg pool for the process, normally created on FastAPI startup and
closed on shutdown via init_pool()/close_pool() (wired into main.py's
lifespan). get_pool() additionally self-initializes on first use if that
hasn't happened yet — ASGI lifespan support on serverless platforms (Vercel's
Python runtime included) isn't something to bet request-correctness on
sight-unseen, especially on a cold start of a fresh instance. The lock makes
concurrent first-requests-on-a-cold-instance wait for one shared pool instead
of racing to create several.

Neon's pooled endpoint (and Supabase's, if this ever moves back) is a
PgBouncer-style transaction pooler: it doesn't support asyncpg's default
prepared-statement caching (a statement prepared on one physical connection
can silently be reused against a different one under the hood, which either
errors or — worse — returns wrong results). `statement_cache_size=0` turns
that caching off. Skipping it works fine locally against a direct Postgres
connection and then breaks in a way that's easy to misdiagnose the moment the
app points at a pooled URL, so it's disabled unconditionally rather than
only when a pooled DSN is detected.

Neon's connection string also carries libpq-specific query params
(`sslmode`, `channel_binding`) that asyncpg's URL parser doesn't understand —
stripped here and replaced with the equivalent `ssl=` kwarg.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import asyncpg

from src.core.config import settings

_pool: asyncpg.Pool | None = None
_init_lock = asyncio.Lock()

_UNSUPPORTED_QUERY_PARAMS = {"sslmode", "channel_binding"}


def _to_asyncpg_dsn(url: str) -> str:
    parts = urlsplit(url)
    kept = [(k, v) for k, v in parse_qsl(parts.query) if k not in _UNSUPPORTED_QUERY_PARAMS]
    return urlunsplit(parts._replace(query=urlencode(kept)))


async def _create_pool() -> asyncpg.Pool:
    return await asyncpg.create_pool(
        _to_asyncpg_dsn(settings.database_url),
        ssl="require",
        min_size=0,
        max_size=10,
        statement_cache_size=0,
    )


async def init_pool() -> None:
    global _pool
    async with _init_lock:
        if _pool is None:
            _pool = await _create_pool()


async def close_pool() -> None:
    global _pool
    async with _init_lock:
        if _pool is not None:
            await _pool.close()
            _pool = None


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        await init_pool()
    assert _pool is not None
    return _pool
