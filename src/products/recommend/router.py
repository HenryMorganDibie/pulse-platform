"""Pulse Platform — /v1/recommend and /v1/catalog/items routes (Product B)."""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends

from src.core.auth import Tenant, get_current_tenant
from src.core.db import get_pool
from src.persona.models import UserState
from src.persona.store import get_or_build_user_state, get_or_create_subject
from src.products.recommend.reasoning import cold_start_strategy, extract_intent, shortlist_candidates
from src.products.recommend.ranking import score_and_rank
from src.products.recommend.retrieval import upsert_catalog_items
from src.schemas.api import (
    CatalogUpsertRequest,
    CatalogUpsertResponse,
    RecommendedItem,
    RecommendRequest,
    RecommendResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Recommend"])


@router.post("/v1/catalog/items", response_model=CatalogUpsertResponse)
async def upsert_catalog(
    request: CatalogUpsertRequest,
    tenant: Tenant = Depends(get_current_tenant),
) -> CatalogUpsertResponse:
    count = await upsert_catalog_items(tenant.id, request.items)
    return CatalogUpsertResponse(upserted=count)


def _decision_factors(user_state: UserState, strategy: str, intent: str) -> List[str]:
    """Deterministic, customer-safe factors — same contract as Simulate's decision_factors."""
    ctx = user_state.contextual
    beh = user_state.behavioural
    factors = [f"Interpreted request as: {intent}"]

    if strategy == "cold_start":
        factors.append("No prior history for this subject — ranked by relevance to the request alone")
    elif strategy == "sparse":
        factors.append("Limited history — widened category range to compensate")
    elif strategy == "cross_domain":
        factors.append(f"Request falls outside their usual categories ({', '.join(ctx.active_categories) or 'none'})")
    else:
        top = sorted(beh.category_affinities, key=beh.category_affinities.get, reverse=True)[:2]
        if top:
            factors.append(f"Ranked using their preference history, especially: {', '.join(top)}")

    return factors


@router.post("/v1/recommend", response_model=RecommendResponse)
async def recommend_endpoint(
    request: RecommendRequest,
    tenant: Tenant = Depends(get_current_tenant),
) -> RecommendResponse:
    subject_id = await get_or_create_subject(tenant.id, request.subject_external_id)
    user_state = await get_or_build_user_state(subject_id)

    intent, intent_trace = await extract_intent(user_state, request.query, request.conversation)
    strategy, strategy_trace = cold_start_strategy(user_state, intent)
    candidates, retrieval_trace = await shortlist_candidates(tenant.id, user_state, intent, strategy)

    ranked, candidates_by_id, ranking_trace = await score_and_rank(candidates, user_state, intent)

    logger.info(
        "recommend trace for subject=%s: %s",
        subject_id,
        intent_trace + strategy_trace + retrieval_trace + ranking_trace,
    )

    recommendations = []
    for idx, scored in enumerate(ranked, start=1):
        candidate = candidates_by_id.get(scored.item_id)
        if candidate is None:
            continue
        recommendations.append(
            RecommendedItem(
                rank=idx,
                item_id=scored.item_id,
                name=candidate.name,
                category=candidate.category,
                predicted_rating=scored.predicted_rating,
                explanation=scored.explanation,
                ndcg_score=scored.ndcg_score,
            )
        )

    pool = get_pool()
    await pool.execute(
        "insert into request_log (tenant_id, subject_id, product) values ($1, $2, 'recommend')",
        tenant.id,
        subject_id,
    )

    return RecommendResponse(
        recommendations=recommendations,
        inferred_intent=intent,
        cold_start=user_state.contextual.is_cold_start,
        decision_factors=_decision_factors(user_state, strategy, intent),
    )
