"""
Pulse Platform — persona construction pipelines.

Ported from pulse-agent/src/agents/persona_agent.py. Same design: three signal
pipelines (behavioural, textual, contextual) run concurrently via
asyncio.gather, each fails independently, and a fallback profile is substituted
for whichever pipeline errors rather than failing the whole request. That
fault-tolerance was one of the genuinely good decisions in the hackathon build
and is unchanged here.

The only real difference from the original: this operates on `ReviewRecord`s
pulled from the `review_records` table (via persona/store.py) instead of a
`review_history` list embedded in every incoming request.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from statistics import mean, stdev
from typing import List, Optional

from src.core.config import settings
from src.persona.llm import call_groq, parse_json_object
from src.persona.models import (
    BehaviouralProfile,
    ContextualProfile,
    ReviewRecord,
    TextualProfile,
    ToneProfile,
    UserState,
    safe_tone,
)

logger = logging.getLogger(__name__)


def _fallback_behavioural() -> BehaviouralProfile:
    return BehaviouralProfile(
        avg_rating=3.0,
        rating_std=0.0,
        category_affinities={},
        recency_weighted_avg=3.0,
        rating_bias=0.0,
        is_harsh_rater=False,
        is_generous_rater=False,
    )


def _fallback_textual() -> TextualProfile:
    return TextualProfile(
        dominant_tone=ToneProfile.MIXED,
        avg_review_length=0,
        sentiment_polarity=0.0,
        vocabulary_richness=0.0,
        uses_first_person=False,
        common_phrases=[],
    )


def _fallback_contextual() -> ContextualProfile:
    return ContextualProfile(
        is_cold_start=True,
        sparse_history=True,
        active_categories=[],
        cross_domain_signals=[],
        recency_days=None,
    )


# ---------------------------------------------------------------------------
# Pipeline 1 — behavioural (pure arithmetic, no LLM call)
# ---------------------------------------------------------------------------

async def _behavioural_pipeline(history: List[ReviewRecord]) -> Optional[BehaviouralProfile]:
    try:
        if not history:
            return _fallback_behavioural()

        ratings = [r.rating for r in history]
        avg = mean(ratings)
        std = stdev(ratings) if len(ratings) > 1 else 0.0

        cat_counts: dict[str, int] = {}
        for r in history:
            cat_counts[r.category] = cat_counts.get(r.category, 0) + 1
        total = sum(cat_counts.values()) or 1
        affinities = {k: v / total for k, v in cat_counts.items()}

        sorted_history = sorted(history, key=lambda r: r.timestamp or "0000", reverse=True)
        weights = [1 / (i + 1) for i in range(len(sorted_history))]
        recency_avg = sum(r.rating * w for r, w in zip(sorted_history, weights)) / sum(weights)

        platform_avg = 3.7
        bias = avg - platform_avg

        return BehaviouralProfile(
            avg_rating=round(avg, 2),
            rating_std=round(std, 2),
            category_affinities=affinities,
            recency_weighted_avg=round(recency_avg, 2),
            rating_bias=round(bias, 2),
            is_harsh_rater=avg < 3.0,
            is_generous_rater=avg >= 4.3,
        )
    except Exception as exc:
        logger.warning("Behavioural pipeline failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Pipeline 2 — textual (one Groq call)
# ---------------------------------------------------------------------------

async def _textual_pipeline(history: List[ReviewRecord]) -> Optional[TextualProfile]:
    try:
        if not history:
            return _fallback_textual()

        corpus = "\n".join(f"[{r.category} · {r.rating}★] {r.text}" for r in history[-10:])

        system = "Return ONLY valid JSON."
        user = f"""Analyze reviews.

Return ONLY:
- dominant_tone: expressive | analytical | terse | narrative | mixed
- avg_review_length: int
- sentiment_polarity: float
- vocabulary_richness: float
- uses_first_person: bool
- common_phrases: list

Reviews:
{corpus}
"""

        raw = await call_groq(system, user, model=settings.persona_model, max_tokens=400)
        data = parse_json_object(raw)

        return TextualProfile(
            dominant_tone=safe_tone(data.get("dominant_tone", "mixed")),
            avg_review_length=int(data.get("avg_review_length", 0)),
            sentiment_polarity=float(data.get("sentiment_polarity", 0.0)),
            vocabulary_richness=float(data.get("vocabulary_richness", 0.0)),
            uses_first_person=bool(data.get("uses_first_person", False)),
            common_phrases=data.get("common_phrases", []),
        )
    except Exception as exc:
        logger.warning("Textual pipeline failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Pipeline 3 — contextual (pure logic, no LLM call)
# ---------------------------------------------------------------------------

async def _contextual_pipeline(history: List[ReviewRecord]) -> Optional[ContextualProfile]:
    try:
        is_cold_start = len(history) == 0
        sparse = len(history) < 5

        active_cats = list({r.category for r in history})

        cat_counts: dict[str, int] = {}
        for r in history:
            cat_counts[r.category] = cat_counts.get(r.category, 0) + 1
        top_cats = sorted(cat_counts, key=cat_counts.get, reverse=True)[:2]
        cross_domain = [c for c in active_cats if c not in top_cats]

        recency_days: Optional[int] = None
        timestamped = [r for r in history if r.timestamp]
        if timestamped:
            latest = max(timestamped, key=lambda r: r.timestamp)
            try:
                last_dt = datetime.fromisoformat(latest.timestamp)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                recency_days = (datetime.now(timezone.utc) - last_dt).days
            except Exception:
                pass

        return ContextualProfile(
            is_cold_start=is_cold_start,
            sparse_history=sparse,
            active_categories=active_cats,
            cross_domain_signals=cross_domain,
            recency_days=recency_days,
        )
    except Exception as exc:
        logger.warning("Contextual pipeline failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

async def build_user_state(subject_id: str, history: List[ReviewRecord]) -> UserState:
    behavioural, textual, contextual = await asyncio.gather(
        _behavioural_pipeline(history),
        _textual_pipeline(history),
        _contextual_pipeline(history),
    )

    pipeline_errors: List[str] = []

    if behavioural is None:
        pipeline_errors.append("behavioural fallback")
        behavioural = _fallback_behavioural()
    if textual is None:
        pipeline_errors.append("textual fallback")
        textual = _fallback_textual()
    if contextual is None:
        pipeline_errors.append("contextual fallback")
        contextual = _fallback_contextual()

    return UserState(
        subject_id=subject_id,
        behavioural=behavioural,
        textual=textual,
        contextual=contextual,
        pipeline_errors=pipeline_errors,
    )
