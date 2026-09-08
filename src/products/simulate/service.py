"""
Pulse Platform — Simulate orchestration, shared by the tenant-authed route
and the admin console's "test as tenant" route.

Both routers resolve a `tenant_id` differently (API key lookup vs. admin
secret + path param) but the actual work — resolve subject, get/build
persona, run the simulation, log the request — is identical, so it lives
here once instead of twice.
"""

from __future__ import annotations

from src.core.db import get_pool
from src.persona.store import get_or_build_user_state, get_or_create_subject
from src.products.simulate.agent import simulate_review
from src.schemas.api import SimulateReviewRequest, SimulateReviewResponse


async def run_simulate(tenant_id: str, request: SimulateReviewRequest) -> SimulateReviewResponse:
    subject_id = await get_or_create_subject(tenant_id, request.subject_external_id)
    user_state = await get_or_build_user_state(subject_id)

    result = await simulate_review(user_state, request.item)

    pool = await get_pool()
    await pool.execute(
        "insert into request_log (tenant_id, subject_id, product) values ($1, $2, 'simulate')",
        tenant_id,
        subject_id,
    )

    return result
