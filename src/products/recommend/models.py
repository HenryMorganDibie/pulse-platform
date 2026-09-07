"""Pulse Platform — internal types shared across the Recommend pipeline."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class CandidateItem(BaseModel):
    item_id: str
    name: str
    category: str
    attributes: Dict[str, Any] = Field(default_factory=dict)
    retrieval_score: float


class ScoredItem(BaseModel):
    item_id: str
    predicted_rating: float
    relevance_score: float
    explanation: str
    ndcg_score: Optional[float] = None
