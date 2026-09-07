"""
Pulse Platform — public API request/response models.

Separate from src/persona/models.py: these are what callers send and receive,
not the internal persona representation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str  # "user" | "assistant"
    content: str


# ---------------------------------------------------------------------------
# Subjects / reviews
# ---------------------------------------------------------------------------

class ReviewRecordIn(BaseModel):
    item_id: str
    category: str
    rating: float = Field(..., ge=1.0, le=5.0)
    text: str = ""
    timestamp: Optional[str] = None


class AddReviewResponse(BaseModel):
    subject_id: str
    status: str = "recorded"


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

class CatalogItemIn(BaseModel):
    item_id: str
    name: str
    category: str
    attributes: Dict[str, Any] = Field(default_factory=dict)


class CatalogUpsertRequest(BaseModel):
    items: List[CatalogItemIn]


class CatalogUpsertResponse(BaseModel):
    upserted: int


# ---------------------------------------------------------------------------
# Simulate — Product A
# ---------------------------------------------------------------------------

class ItemDetailsIn(BaseModel):
    item_id: str
    name: str
    category: str
    description: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)


class SimulateReviewRequest(BaseModel):
    subject_external_id: str
    item: ItemDetailsIn


class SimulateReviewResponse(BaseModel):
    simulated_rating: float = Field(..., ge=1.0, le=5.0)
    simulated_review: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    # Deterministic, customer-safe factors derived from the persona profile —
    # never raw model chain-of-thought or internal error/fallback text. See
    # src/products/simulate/agent.py::_decision_factors.
    decision_factors: List[str]


# ---------------------------------------------------------------------------
# Recommend — Product B
# ---------------------------------------------------------------------------

class RecommendRequest(BaseModel):
    subject_external_id: str
    query: Optional[str] = None
    conversation: List[Message] = Field(default_factory=list)


class RecommendedItem(BaseModel):
    rank: int
    item_id: str
    name: str
    category: str
    predicted_rating: float = Field(..., ge=1.0, le=5.0)
    explanation: str
    ndcg_score: Optional[float] = None


class RecommendResponse(BaseModel):
    recommendations: List[RecommendedItem]
    inferred_intent: str
    cold_start: bool
    # Same customer-safe-factors contract as SimulateReviewResponse.decision_factors.
    decision_factors: List[str]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
