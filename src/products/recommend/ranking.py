"""
Pulse Platform — Recommend product, scoring and ranking.

Ported from pulse-agent/src/agents/ranking_agent.py: LLM-scored relevance,
dedup/diversity pass, and self-referential NDCG@k (computed against the same
LLM's own relevance scores — a consistency check, not evidence of quality
against real user behavior; see CONTRACTS.md). Per-item `explanation` text is
already designed to be short and customer-facing in the original prompt, so
it's kept as-is; only the internal `trace` (fallback/exception detail) is not
part of the returned response — see reasoning.py's decision_factors handling
in the router for the same "internal log vs. customer-safe output" split used
in the Simulate product.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from src.persona.llm import call_llm, parse_json_array
from src.persona.models import UserState
from src.products.recommend.models import CandidateItem, ScoredItem

logger = logging.getLogger(__name__)

_TOP_K = 5


def _candidate_summary(candidate: CandidateItem) -> str:
    attrs = ", ".join(f"{k}={v}" for k, v in list(candidate.attributes.items())[:3])
    return f"[{candidate.item_id}] {candidate.name} ({candidate.category}) {attrs}"


async def _score_and_rank(
    candidates: List[CandidateItem],
    user_state: UserState,
    intent: str,
) -> Tuple[List[ScoredItem], List[str]]:
    trace: List[str] = []

    if not candidates:
        return [], ["No candidates to score"]

    beh = user_state.behavioural
    candidate_list = "\n".join(f"{i+1}. {_candidate_summary(c)}" for i, c in enumerate(candidates[:8]))

    system = """You are a recommendation engine.
CRITICAL:
- Output ONLY a JSON array
- No markdown, no commentary
- Keep explanations SHORT and customer-facing (max ~15 words)"""

    user_prompt = f"""User avg rating: {beh.avg_rating:.1f}
Intent: {intent}

Items:
{candidate_list}

Return EXACT JSON array, max {_TOP_K} items:
[{{"item_id":"i_001","predicted_rating":4.2,"relevance_score":0.84,"explanation":"Good category match."}}]

Rules: predicted_rating 1-5, relevance_score 0-1, explanation is short and safe to show the end user directly.
"""

    try:
        raw = await call_llm(system, user_prompt, tier="fast", max_tokens=350)
    except Exception as exc:
        trace.append(f"Groq scoring call failed: {exc}")
        return [], trace

    data = parse_json_array(raw)
    scored: List[ScoredItem] = []

    for item in data:
        try:
            scored.append(
                ScoredItem(
                    item_id=str(item.get("item_id", "")),
                    predicted_rating=round(min(5.0, max(1.0, float(item.get("predicted_rating", beh.avg_rating)))), 1),
                    relevance_score=round(min(1.0, max(0.0, float(item.get("relevance_score", 0.5)))), 3),
                    explanation=str(item.get("explanation", "Good match."))[:100],
                )
            )
        except Exception:
            continue

    trace.append(f"Scored {len(scored)} items")
    return scored, trace


def _dedup_and_sort(scored_items: List[ScoredItem], top_k: int = _TOP_K) -> List[ScoredItem]:
    seen = set()
    deduped = []
    for item in scored_items:
        if item.item_id not in seen:
            seen.add(item.item_id)
            deduped.append(item)
    deduped.sort(key=lambda x: x.relevance_score, reverse=True)
    return deduped[:top_k]


def _assign_ndcg(items: List[ScoredItem]) -> List[ScoredItem]:
    if not items:
        return []

    ideal = sorted((i.relevance_score for i in items), reverse=True)
    ideal_dcg = sum(rel / (i + 2) for i, rel in enumerate(ideal)) or 1.0

    result = []
    for i, item in enumerate(items):
        dcg = item.relevance_score / (i + 2)
        result.append(item.model_copy(update={"ndcg_score": round(min(1.0, dcg / ideal_dcg), 4)}))
    return result


def _fallback_ranking(candidates: List[CandidateItem], user_state: UserState, top_k: int = _TOP_K) -> List[ScoredItem]:
    ranked = sorted(candidates, key=lambda c: c.retrieval_score, reverse=True)[:top_k]
    return [
        ScoredItem(
            item_id=c.item_id,
            predicted_rating=round(user_state.behavioural.avg_rating, 1),
            relevance_score=c.retrieval_score,
            explanation=f"Matches {c.category}",
        )
        for c in ranked
    ]


async def score_and_rank(
    candidates: List[CandidateItem],
    user_state: UserState,
    intent: str,
) -> Tuple[List[ScoredItem], Dict[str, CandidateItem], List[str]]:
    candidates_by_id = {c.item_id: c for c in candidates}

    scored, trace = await _score_and_rank(candidates, user_state, intent)

    if not scored:
        trace.append("Using fallback ranking (retrieval-score ordering)")
        scored = _fallback_ranking(candidates, user_state)

    ranked = _assign_ndcg(_dedup_and_sort(scored))
    return ranked, candidates_by_id, trace
