"""Pulse Platform — /v1/subjects/{external_id}/reviews route (shared persona core)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.core.auth import Tenant, get_current_tenant
from src.persona.models import ReviewRecord
from src.persona.store import add_review_record, get_or_create_subject
from src.schemas.api import AddReviewResponse, ReviewRecordIn

router = APIRouter(tags=["Subjects"])


@router.post("/v1/subjects/{external_id}/reviews", response_model=AddReviewResponse)
async def add_review(
    external_id: str,
    review: ReviewRecordIn,
    tenant: Tenant = Depends(get_current_tenant),
) -> AddReviewResponse:
    subject_id = await get_or_create_subject(tenant.id, external_id)
    await add_review_record(
        subject_id,
        ReviewRecord(
            item_id=review.item_id,
            category=review.category,
            rating=review.rating,
            text=review.text,
            timestamp=review.timestamp,
        ),
    )
    return AddReviewResponse(subject_id=subject_id)
