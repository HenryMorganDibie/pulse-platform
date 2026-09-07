"""
Pulse Platform — persona domain types.

Ported from pulse-agent/src/schemas/models.py. The pipelines and the shape of
UserState are unchanged from the hackathon version — that part of the design
was sound. What changes is that UserState is now a cached row in `user_states`
instead of something rebuilt from scratch on every request.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ToneProfile(str, Enum):
    EXPRESSIVE = "expressive"
    ANALYTICAL = "analytical"
    TERSE = "terse"
    NARRATIVE = "narrative"
    NIGERIAN = "nigerian"
    MIXED = "mixed"


class ReviewRecord(BaseModel):
    """A single historical review written by a subject."""

    item_id: str
    category: str
    rating: float = Field(..., ge=1.0, le=5.0)
    text: str = ""
    timestamp: Optional[str] = None


class BehaviouralProfile(BaseModel):
    avg_rating: float
    rating_std: float
    category_affinities: Dict[str, float]
    recency_weighted_avg: float
    rating_bias: float
    is_harsh_rater: bool
    is_generous_rater: bool


class TextualProfile(BaseModel):
    dominant_tone: ToneProfile
    avg_review_length: int
    sentiment_polarity: float
    vocabulary_richness: float
    uses_first_person: bool
    common_phrases: List[str] = Field(default_factory=list)


class ContextualProfile(BaseModel):
    is_cold_start: bool
    sparse_history: bool
    active_categories: List[str]
    cross_domain_signals: List[str]
    recency_days: Optional[int] = None


class UserState(BaseModel):
    """Fully constructed persona — cached in `user_states`, shared by both products."""

    subject_id: str
    behavioural: BehaviouralProfile
    textual: TextualProfile
    contextual: ContextualProfile
    pipeline_errors: List[str] = Field(default_factory=list)


ALLOWED_TONES = {t.value for t in ToneProfile if t != ToneProfile.NIGERIAN} | {"nigerian"}


def safe_tone(value: Any) -> ToneProfile:
    if isinstance(value, str) and value in ALLOWED_TONES:
        return ToneProfile(value)
    return ToneProfile.MIXED
