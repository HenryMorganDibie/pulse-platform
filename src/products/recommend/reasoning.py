"""
Pulse Platform — Recommend product, intent + cold-start reasoning.

Ported from pulse-agent/src/agents/reasoning_agent.py: intent extraction from
the query/conversation, cold-start/sparse/cross-domain strategy selection, and
candidate shortlisting. The strategy logic and prompt are unchanged; retrieval
now calls the pgvector-backed retrieve_candidates instead of the old
keyword-overlap version, and everything is tenant-scoped.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from src.persona.llm import call_llm, parse_json_object
from src.persona.models import UserState
from src.products.recommend.models import CandidateItem
from src.products.recommend.retrieval import retrieve_candidates
from src.schemas.api import Message

logger = logging.getLogger(__name__)


def _format_conversation(history: List[Message]) -> str:
    if not history:
        return "(no conversation history)"
    return "\n".join(f"{m.role.upper()}: {m.content}" for m in history[-6:])


async def extract_intent(
    user_state: UserState,
    query: str | None,
    conversation: List[Message],
) -> Tuple[str, List[str]]:
    """Returns (intent, trace) — trace is for logs only, never returned to callers."""
    trace: List[str] = []
    beh = user_state.behavioural
    ctx = user_state.contextual

    system = (
        "You are an intent extraction engine for a recommendation system. "
        "Given a user's profile, an explicit query (if any), and conversation history, "
        "infer what they want. Return ONLY valid JSON — no preamble, no markdown fences."
    )

    user_prompt = f"""Extract the user's recommendation intent.
Be specific — capture the actual mood, occasion, constraints, and preferences expressed.
Do not produce vague intents like "general recommendation".

User profile:
- Known categories (most reviewed first): {list(beh.category_affinities.keys())}
- Is new user (cold-start): {ctx.is_cold_start}
- Avg rating: {beh.avg_rating} | generous_rater: {beh.is_generous_rater} | harsh_rater: {beh.is_harsh_rater}
- Cross-domain signals: {ctx.cross_domain_signals}

Explicit query: {query or "(none)"}

Conversation history:
{_format_conversation(conversation)}

Return JSON with exactly these keys:
- intent: string — specific intent capturing occasion + mood + constraints
- target_categories: list of 1-3 category strings most relevant to this request
- is_cross_domain: boolean — true if the request targets a category the user has rarely or never reviewed
"""

    try:
        raw = await call_llm(system, user_prompt, tier="persona", max_tokens=250)
        data = parse_json_object(raw)

        intent = data.get("intent", "general recommendation")
        target_cats = data.get("target_categories", list(beh.category_affinities.keys())[:2])
        is_cross = data.get("is_cross_domain", False)

        trace.append(f"Intent extracted: \"{intent}\" target_categories={target_cats}")
        if is_cross:
            trace.append("Cross-domain request detected")

        return intent, trace
    except Exception as exc:
        trace.append(f"Intent extraction fallback: {exc}")
        return query or "general recommendation", trace


def cold_start_strategy(user_state: UserState, intent: str) -> Tuple[str, List[str]]:
    trace: List[str] = []
    ctx = user_state.contextual
    beh = user_state.behavioural

    if ctx.is_cold_start:
        strategy = "cold_start"
        trace.append("Cold-start strategy: new subject — popularity + intent matching")
    elif ctx.sparse_history:
        strategy = "sparse"
        trace.append("Sparse-history strategy: < 5 reviews — widening category net")
    elif intent and not any(cat.lower() in intent.lower() for cat in ctx.active_categories):
        strategy = "cross_domain"
        trace.append(f"Cross-domain strategy: known={ctx.active_categories}, cross={ctx.cross_domain_signals}")
    else:
        strategy = "normal"
        trace.append(f"Normal strategy: {len(beh.category_affinities)} known categories")

    return strategy, trace


async def shortlist_candidates(
    tenant_id: str,
    user_state: UserState,
    intent: str,
    strategy: str,
    n: int = 15,
) -> Tuple[List[CandidateItem], List[str]]:
    trace: List[str] = []

    if strategy == "sparse":
        candidates = await retrieve_candidates(tenant_id, user_state, intent, n=n + 5)
        candidates = candidates[:n]
    else:
        candidates = await retrieve_candidates(tenant_id, user_state, intent, n=n)

    trace.append(f"{strategy} retrieval: {len(candidates)} candidates")
    return candidates, trace
