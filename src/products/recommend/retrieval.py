"""
Pulse Platform — catalog upsert and pgvector retrieval.

Replaces pulse-agent/src/tools/retrieval_tool.py's keyword-token-overlap
scoring with real cosine similarity search over pgvector, scoped per tenant.
Final candidate score still blends in category affinity from the persona —
that part of the old scoring formula (category affinity as a real signal, not
just semantic similarity) was a reasonable idea, just previously computed
against fake "similarity."
"""

from __future__ import annotations

import json
import logging
from typing import List

from src.core.config import settings
from src.core.db import get_pool
from src.persona.models import UserState
from src.products.recommend.embeddings import embed_text
from src.products.recommend.models import CandidateItem
from src.schemas.api import CatalogItemIn

logger = logging.getLogger(__name__)


def _item_text(item: CatalogItemIn) -> str:
    attr_str = " ".join(f"{k}: {v}" for k, v in item.attributes.items())
    return f"{item.name}. {item.category}. {attr_str}".strip()


async def upsert_catalog_items(tenant_id: str, items: List[CatalogItemIn]) -> int:
    pool = await get_pool()
    count = 0

    for item in items:
        vector = await embed_text(_item_text(item))
        await pool.execute(
            """
            insert into catalog_items (tenant_id, item_id, name, category, attributes, embedding, embedding_model, updated_at)
            values ($1, $2, $3, $4, $5, $6, $7, now())
            on conflict (tenant_id, item_id) do update set
                name = excluded.name,
                category = excluded.category,
                attributes = excluded.attributes,
                embedding = excluded.embedding,
                embedding_model = excluded.embedding_model,
                updated_at = now()
            """,
            tenant_id,
            item.item_id,
            item.name,
            item.category,
            json.dumps(item.attributes),
            str(vector),
            settings.embedding_model,
        )
        count += 1

    return count


def _category_affinity_score(category: str, user_state: UserState) -> float:
    affinities = user_state.behavioural.category_affinities
    if category in affinities:
        return affinities[category]
    if category in user_state.contextual.cross_domain_signals:
        return 0.3
    return 0.1


async def retrieve_candidates(
    tenant_id: str,
    user_state: UserState,
    query: str,
    n: int = 15,
) -> List[CandidateItem]:
    query_text = query.strip() if query and query.strip() else _fallback_query(user_state)
    query_vector = await embed_text(query_text)

    pool = await get_pool()
    # Over-fetch on semantic similarity, then re-rank blending in category
    # affinity, so a strong persona signal can surface an item that wasn't the
    # single closest embedding match.
    rows = await pool.fetch(
        """
        select item_id, name, category, attributes,
               1 - (embedding <=> $2) as similarity
        from catalog_items
        where tenant_id = $1 and embedding is not null
        order by embedding <=> $2
        limit $3
        """,
        tenant_id,
        str(query_vector),
        max(n * 3, 30),
    )

    scored: List[tuple[float, dict]] = []
    for row in rows:
        similarity = float(row["similarity"])
        affinity = _category_affinity_score(row["category"], user_state)
        total = (similarity * 0.7) + (affinity * 0.3)
        scored.append((total, row))

    scored.sort(key=lambda x: x[0], reverse=True)

    candidates = [
        CandidateItem(
            item_id=row["item_id"],
            name=row["name"],
            category=row["category"],
            attributes=json.loads(row["attributes"]) if isinstance(row["attributes"], str) else row["attributes"],
            retrieval_score=round(score, 4),
        )
        for score, row in scored[:n]
    ]

    logger.info("retrieve_candidates: tenant=%s query=%r -> %d candidates", tenant_id, query_text[:60], len(candidates))
    return candidates


def _fallback_query(user_state: UserState) -> str:
    """No explicit query/conversation — synthesize one from the persona's top categories."""
    affinities = user_state.behavioural.category_affinities
    if not affinities:
        return "popular recommended items"
    top = sorted(affinities, key=affinities.get, reverse=True)[:2]
    return " ".join(top)
