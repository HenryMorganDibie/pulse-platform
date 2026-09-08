"""
Pulse Platform — admin console API.

Everything here is gated by require_admin (a single operator secret, see
src/core/admin_auth.py) rather than the tenant API-key auth every /v1/*
route uses. Tenant creation/listing/key-revocation mirrors
scripts/create_tenant.py and scripts/revoke_api_key.py exactly — those CLI
scripts stay as a break-glass path independent of a running API instance,
this is the same operations available over HTTP for the admin frontend.

The "test as tenant" routes (simulate-review, recommend, catalog upsert)
deliberately take tenant_id as a path param instead of requiring the
tenant's real API key: that key is intentionally never retrievable after
creation (see TenantCreateResponse), so an admin console that could only
test using a tenant's actual key would be unusable for exactly the tenants
it's most useful for testing. Trust here comes from the admin secret, not
from re-deriving a tenant credential.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from src.core.admin_auth import require_admin
from src.core.api_keys import generate_api_key, hash_api_key
from src.core.db import get_pool
from src.products.recommend.retrieval import upsert_catalog_items
from src.products.recommend.service import run_recommend
from src.products.simulate.service import run_simulate
from src.schemas.admin import (
    KeyListResponse,
    KeySummary,
    MintKeyResponse,
    RevokeKeyResponse,
    TenantCreateRequest,
    TenantCreateResponse,
    TenantListResponse,
    TenantSummary,
)
from src.schemas.api import (
    CatalogUpsertRequest,
    CatalogUpsertResponse,
    RecommendRequest,
    RecommendResponse,
    SimulateReviewRequest,
    SimulateReviewResponse,
)

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_admin)])


@router.post("/tenants", response_model=TenantCreateResponse)
async def create_tenant(request: TenantCreateRequest) -> TenantCreateResponse:
    pool = await get_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            tenant_id = await conn.fetchval(
                "insert into tenants (name) values ($1) returning id",
                request.name,
            )

            full_key, prefix = generate_api_key()
            await conn.execute(
                "insert into api_keys (tenant_id, key_hash, key_prefix) values ($1, $2, $3)",
                tenant_id,
                hash_api_key(full_key),
                prefix,
            )

    return TenantCreateResponse(
        tenant_id=str(tenant_id),
        name=request.name,
        api_key=full_key,
        key_prefix=prefix,
    )


@router.get("/tenants", response_model=TenantListResponse)
async def list_tenants() -> TenantListResponse:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        select t.id, t.name, t.plan, t.created_at,
               count(k.id) filter (where k.revoked_at is null) as active_key_count
        from tenants t
        left join api_keys k on k.tenant_id = t.id
        group by t.id, t.name, t.plan, t.created_at
        order by t.created_at desc
        """
    )
    return TenantListResponse(
        tenants=[
            TenantSummary(
                tenant_id=str(r["id"]),
                name=r["name"],
                plan=r["plan"],
                created_at=r["created_at"],
                active_key_count=r["active_key_count"],
            )
            for r in rows
        ]
    )


@router.get("/tenants/{tenant_id}/keys", response_model=KeyListResponse)
async def list_keys(tenant_id: str) -> KeyListResponse:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        select key_prefix, created_at, revoked_at
        from api_keys
        where tenant_id = $1
        order by created_at desc
        """,
        tenant_id,
    )
    return KeyListResponse(
        keys=[
            KeySummary(key_prefix=r["key_prefix"], created_at=r["created_at"], revoked_at=r["revoked_at"])
            for r in rows
        ]
    )


@router.post("/tenants/{tenant_id}/keys", response_model=MintKeyResponse)
async def mint_key(tenant_id: str) -> MintKeyResponse:
    pool = await get_pool()

    exists = await pool.fetchval("select 1 from tenants where id = $1", tenant_id)
    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    full_key, prefix = generate_api_key()
    await pool.execute(
        "insert into api_keys (tenant_id, key_hash, key_prefix) values ($1, $2, $3)",
        tenant_id,
        hash_api_key(full_key),
        prefix,
    )
    return MintKeyResponse(api_key=full_key, key_prefix=prefix)


@router.post("/keys/{key_prefix}/revoke", response_model=RevokeKeyResponse)
async def revoke_key(key_prefix: str) -> RevokeKeyResponse:
    pool = await get_pool()
    result = await pool.execute(
        "update api_keys set revoked_at = now() where key_prefix = $1 and revoked_at is null",
        key_prefix,
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active key with that prefix")
    return RevokeKeyResponse(status="revoked")


@router.post("/tenants/{tenant_id}/catalog/items", response_model=CatalogUpsertResponse)
async def admin_upsert_catalog(tenant_id: str, request: CatalogUpsertRequest) -> CatalogUpsertResponse:
    count = await upsert_catalog_items(tenant_id, request.items)
    return CatalogUpsertResponse(upserted=count)


@router.post("/tenants/{tenant_id}/simulate-review", response_model=SimulateReviewResponse)
async def admin_simulate_review(tenant_id: str, request: SimulateReviewRequest) -> SimulateReviewResponse:
    return await run_simulate(tenant_id, request)


@router.post("/tenants/{tenant_id}/recommend", response_model=RecommendResponse)
async def admin_recommend(tenant_id: str, request: RecommendRequest) -> RecommendResponse:
    return await run_recommend(tenant_id, request)
