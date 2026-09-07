"""
Pulse Platform — Simulate product (Product A, the flagship product).

Ported from pulse-agent/src/agents/review_agent.py. Given a subject's cached
UserState and an unseen item, predicts the rating that subject would give,
generates a review in their tone, and scores the review's behavioural fidelity.
Same 3-step structure and same safe-fallback-at-every-step approach as the
original — that part of the hackathon build held up under review. See
CONTRACTS.md for exactly what was ported unchanged vs. adapted.

Two separate outputs, deliberately not conflated:
  - `trace`: internal engineering log (LLM reasoning text, fallback/exception
    detail). Logged via `logger`, never returned from the API — it's for our
    debugging, and raw model chain-of-thought / stack traces are not
    something a customer-facing product should expose.
  - `decision_factors`: a short, deterministic list of customer-safe factors
    derived directly from the persona profile (never from LLM free text or
    exception messages). This is what SimulateReviewResponse actually returns.
"""

from __future__ import annotations

import logging
from typing import List, Tuple

from src.core.config import settings
from src.persona.llm import call_groq, parse_json_object
from src.persona.models import ToneProfile, UserState
from src.schemas.api import ItemDetailsIn, SimulateReviewResponse

logger = logging.getLogger(__name__)

_TONE_INSTRUCTIONS = {
    ToneProfile.EXPRESSIVE: "Emotional and opinionated.",
    ToneProfile.ANALYTICAL: "Factual and measured.",
    ToneProfile.TERSE: "Very short and concise.",
    ToneProfile.NARRATIVE: "Tell a brief story.",
    ToneProfile.NIGERIAN: (
        "Write in Nigerian English style. Use warm, direct language with occasional "
        "pidgin expressions (e.g. 'sha', 'abeg', 'no be small thing', 'e sweet me'). "
        "Be enthusiastic and communal in tone, like recommending to a friend."
    ),
    ToneProfile.MIXED: "Natural conversational tone.",
}


def _item_description(item: ItemDetailsIn) -> str:
    parts = [f"{item.name} ({item.category})"]
    if item.description:
        parts.append(item.description)
    return " — ".join(parts)


async def _infer_rating(user_state: UserState, item: ItemDetailsIn) -> Tuple[float, List[str]]:
    trace: List[str] = []
    beh = user_state.behavioural

    anchor = beh.recency_weighted_avg or beh.avg_rating
    adjusted_anchor = round(min(5.0, max(1.0, anchor + (beh.rating_bias * 0.3))), 1)
    trace.append(f"Anchor rating={adjusted_anchor}")

    system = "You predict user ratings. Return ONLY valid JSON."
    user_prompt = f"""User avg rating: {beh.avg_rating}
Rating bias: {beh.rating_bias:+.2f}
Item: {_item_description(item)}

Return:
{{"predicted_rating": 4.2, "confidence": 0.8, "reasoning": "Short reason"}}
"""

    try:
        raw = await call_groq(system, user_prompt, model=settings.fast_model, max_tokens=120)
        data = parse_json_object(raw)

        predicted = round(
            min(5.0, max(1.0, float(data.get("predicted_rating", adjusted_anchor)))), 1
        )
        confidence = float(data.get("confidence", 0.7))
        reasoning = str(data.get("reasoning", "Based on user history."))

        trace.append(f"Predicted={predicted}, confidence={confidence:.2f}, reasoning={reasoning}")
        return predicted, trace
    except Exception as exc:
        trace.append(f"Fallback rating used: {exc}")
        return adjusted_anchor, trace


async def _generate_review(
    user_state: UserState, item: ItemDetailsIn, predicted_rating: float
) -> Tuple[str, List[str]]:
    trace: List[str] = []
    txt = user_state.textual
    tone_instruction = _TONE_INSTRUCTIONS.get(txt.dominant_tone, _TONE_INSTRUCTIONS[ToneProfile.MIXED])
    avg_len = min(txt.avg_review_length or 60, 80)

    system = "You generate realistic reviews. Return ONLY valid JSON."
    user_prompt = f"""Write a realistic review.
Tone: {tone_instruction}
Rating: {predicted_rating} stars
Item: {_item_description(item)}
Length: ~{avg_len} words

Return:
{{"review_text": "review here", "word_count": 50}}
"""

    try:
        raw = await call_groq(system, user_prompt, model=settings.fast_model, max_tokens=220)
        data = parse_json_object(raw)

        review_text = str(data.get("review_text", "")).strip()
        if not review_text:
            review_text = f"I enjoyed {item.name}. It matched my expectations overall."

        word_count = int(data.get("word_count", len(review_text.split())))
        trace.append(f"Generated review ({word_count} words)")
        return review_text, trace
    except Exception as exc:
        fallback = f"I enjoyed {item.name}. The experience was decent overall."
        trace.append(f"Fallback review used: {exc}")
        return fallback, trace


async def _score_quality(review_text: str) -> Tuple[float, List[str]]:
    trace: List[str] = []
    system = "Score behavioural fidelity. Return ONLY JSON."
    user_prompt = f"""Review:
{review_text[:300]}

Return:
{{"quality_score": 0.82, "notes": "Short note"}}
"""

    try:
        raw = await call_groq(system, user_prompt, model=settings.fast_model, max_tokens=100)
        data = parse_json_object(raw)

        score = round(min(1.0, max(0.0, float(data.get("quality_score", 0.75)))), 2)
        notes = str(data.get("notes", ""))
        trace.append(f"Quality={score}")
        if notes:
            trace.append(notes)
        return score, trace
    except Exception as exc:
        trace.append(f"Fallback quality used: {exc}")
        return 0.75, trace


def _decision_factors(user_state: UserState, item: ItemDetailsIn, predicted_rating: float) -> List[str]:
    """
    Deterministic, customer-safe explanation of the result — built directly
    from the persona profile, never from LLM free text. This is what actually
    goes out over the API; `trace` above is for logs only.
    """
    beh = user_state.behavioural
    ctx = user_state.contextual
    factors: List[str] = []

    affinity = beh.category_affinities.get(item.category)
    if affinity is not None and affinity > 0:
        factors.append(f"Has a history of rating {item.category} items ({affinity:.0%} of past reviews)")
    elif ctx.is_cold_start:
        factors.append("No prior history for this subject — rating anchored to platform baseline")
    else:
        factors.append(f"No prior {item.category} history — extrapolated from overall rating pattern")

    if beh.is_generous_rater:
        factors.append("Tends to rate generously (avg ≥ 4.3)")
    elif beh.is_harsh_rater:
        factors.append("Tends to rate critically (avg < 3.0)")

    if abs(beh.rating_bias) >= 0.3:
        direction = "above" if beh.rating_bias > 0 else "below"
        factors.append(f"Historically rates {direction} platform average by {abs(beh.rating_bias):.1f}")

    factors.append(f"Review generated in their established tone: {user_state.textual.dominant_tone.value}")

    return factors


async def simulate_review(user_state: UserState, item: ItemDetailsIn) -> SimulateReviewResponse:
    trace: List[str] = [
        f"Persona: avg_rating={user_state.behavioural.avg_rating}, "
        f"tone={user_state.textual.dominant_tone.value}, "
        f"cold_start={user_state.contextual.is_cold_start}"
    ]

    try:
        predicted_rating, rating_trace = await _infer_rating(user_state, item)
        trace.extend(rating_trace)

        review_text, gen_trace = await _generate_review(user_state, item, predicted_rating)
        trace.extend(gen_trace)

        quality_score, quality_trace = await _score_quality(review_text)
        trace.extend(quality_trace)

        logger.info("simulate_review trace for subject=%s: %s", user_state.subject_id, trace)

        return SimulateReviewResponse(
            simulated_rating=predicted_rating,
            simulated_review=review_text,
            confidence=quality_score,
            decision_factors=_decision_factors(user_state, item, predicted_rating),
        )
    except Exception as exc:
        logger.error("simulate_review failed for subject=%s: %s", user_state.subject_id, exc)
        fallback_rating = round(user_state.behavioural.avg_rating, 1)
        return SimulateReviewResponse(
            simulated_rating=fallback_rating,
            simulated_review=f"I tried {item.name}. It was okay overall.",
            confidence=0.7,
            decision_factors=["Insufficient signal — used the subject's overall average rating"],
        )
