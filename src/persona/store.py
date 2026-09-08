"""
Pulse Platform — persona persistence and caching.

This module is the fix for pulse-agent's biggest cost/latency problem: the old
code rebuilt UserState (3 pipelines, 1 Groq call) on every single API request.
Here, `get_or_build_user_state` only touches the pipelines on a cache miss or
an explicit staleness flag — otherwise it's one indexed row read.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

import asyncpg

from src.core.db import get_pool
from src.persona.models import (
    BehaviouralProfile,
    ContextualProfile,
    ReviewRecord,
    TextualProfile,
    UserState,
)
from src.persona.pipelines import build_user_state

logger = logging.getLogger(__name__)


async def get_or_create_subject(tenant_id: str, external_id: str) -> str:
    pool = get_pool()
    row = await pool.fetchrow(
        """
        insert into subjects (tenant_id, external_id)
        values ($1, $2)
        on conflict (tenant_id, external_id) do update set external_id = excluded.external_id
        returning id
        """,
        tenant_id,
        external_id,
    )
    return str(row["id"])


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    """asyncpg needs an actual datetime for a timestamptz param, not an ISO string."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        logger.warning("Unparseable review timestamp %r — storing as null", value)
        return None


async def add_review_record(subject_id: str, record: ReviewRecord) -> None:
    """Append a review and mark the cached persona stale so it's rebuilt on next read."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                insert into review_records (subject_id, item_id, category, rating, text, timestamp)
                values ($1, $2, $3, $4, $5, $6)
                """,
                subject_id,
                record.item_id,
                record.category,
                record.rating,
                record.text,
                _parse_timestamp(record.timestamp),
            )
            await conn.execute(
                "update user_states set stale = true where subject_id = $1",
                subject_id,
            )


async def _fetch_history(conn: asyncpg.Connection, subject_id: str) -> List[ReviewRecord]:
    rows = await conn.fetch(
        """
        select item_id, category, rating, text, timestamp
        from review_records
        where subject_id = $1
        order by coalesce(timestamp, created_at) asc
        """,
        subject_id,
    )
    return [
        ReviewRecord(
            item_id=r["item_id"],
            category=r["category"],
            rating=float(r["rating"]),
            text=r["text"],
            timestamp=r["timestamp"].isoformat() if r["timestamp"] else None,
        )
        for r in rows
    ]


async def get_or_build_user_state(subject_id: str) -> UserState:
    pool = get_pool()

    async with pool.acquire() as conn:
        cached = await conn.fetchrow(
            """
            select behavioural, textual, contextual, pipeline_errors, stale
            from user_states
            where subject_id = $1
            """,
            subject_id,
        )

        if cached is not None and not cached["stale"]:
            return UserState(
                subject_id=subject_id,
                behavioural=BehaviouralProfile(**json.loads(cached["behavioural"])),
                textual=TextualProfile(**json.loads(cached["textual"])),
                contextual=ContextualProfile(**json.loads(cached["contextual"])),
                pipeline_errors=json.loads(cached["pipeline_errors"]),
            )

        history = await _fetch_history(conn, subject_id)

    user_state = await build_user_state(subject_id, history)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            insert into user_states (subject_id, behavioural, textual, contextual, pipeline_errors, stale)
            values ($1, $2, $3, $4, $5, false)
            on conflict (subject_id) do update set
                behavioural = excluded.behavioural,
                textual = excluded.textual,
                contextual = excluded.contextual,
                pipeline_errors = excluded.pipeline_errors,
                computed_at = now(),
                stale = false
            """,
            subject_id,
            user_state.behavioural.model_dump_json(),
            user_state.textual.model_dump_json(),
            user_state.contextual.model_dump_json(),
            json.dumps(user_state.pipeline_errors),
        )

    return user_state
