"""Pulse Platform — /v1/simulate-review route (Product A)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.core.auth import Tenant, get_current_tenant
from src.products.simulate.service import run_simulate
from src.schemas.api import SimulateReviewRequest, SimulateReviewResponse

router = APIRouter(tags=["Simulate"])


@router.post("/v1/simulate-review", response_model=SimulateReviewResponse)
async def simulate_review_endpoint(
    request: SimulateReviewRequest,
    tenant: Tenant = Depends(get_current_tenant),
) -> SimulateReviewResponse:
    return await run_simulate(tenant.id, request)
