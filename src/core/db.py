"""
Pulse Platform — Postgres connection pool.

One asyncpg pool for the process, created on FastAPI startup and closed on
shutdown. Every query goes through this — no per-request connections.

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

from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import asyncpg

from src.core.config import settings

_pool: asyncpg.Pool | None = None

_UNSUPPORTED_QUERY_PARAMS = {"sslmode", "channel_binding"}


def _to_asyncpg_dsn(url: str) -> str:
    parts = urlsplit(url)
    kept = [(k, v) for k, v in parse_qsl(parts.query) if k not in _UNSUPPORTED_QUERY_PARAMS]
    return urlunsplit(parts._replace(query=urlencode(kept)))


async def init_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        _to_asyncpg_dsn(settings.database_url),
        ssl="require",
        min_size=0,
        max_size=10,
        statement_cache_size=0,
    )


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call init_pool() on startup first")
    return _pool
