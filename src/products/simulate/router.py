"""Pulse Platform — /v1/simulate-review route (Product A)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.core.auth import Tenant, get_current_tenant
from src.core.db import get_pool
from src.persona.store import get_or_build_user_state, get_or_create_subject
from src.products.simulate.agent import simulate_review
from src.schemas.api import SimulateReviewRequest, SimulateReviewResponse

router = APIRouter(tags=["Simulate"])


@router.post("/v1/simulate-review", response_model=SimulateReviewResponse)
async def simulate_review_endpoint(
    request: SimulateReviewRequest,
    tenant: Tenant = Depends(get_current_tenant),
) -> SimulateReviewResponse:
    subject_id = await get_or_create_subject(tenant.id, request.subject_external_id)
    user_state = await get_or_build_user_state(subject_id)

    result = await simulate_review(user_state, request.item)

    pool = get_pool()
    await pool.execute(
        "insert into request_log (tenant_id, subject_id, product) values ($1, $2, 'simulate')",
        tenant.id,
        subject_id,
    )

    return result
