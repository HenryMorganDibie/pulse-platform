"""Pulse Platform — /v1/recommend and /v1/catalog/items routes (Product B)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.core.auth import Tenant, get_current_tenant
from src.products.recommend.retrieval import upsert_catalog_items
from src.products.recommend.service import run_recommend
from src.schemas.api import (
    CatalogUpsertRequest,
    CatalogUpsertResponse,
    RecommendRequest,
    RecommendResponse,
)

router = APIRouter(tags=["Recommend"])


@router.post("/v1/catalog/items", response_model=CatalogUpsertResponse)
async def upsert_catalog(
    request: CatalogUpsertRequest,
    tenant: Tenant = Depends(get_current_tenant),
) -> CatalogUpsertResponse:
    count = await upsert_catalog_items(tenant.id, request.items)
    return CatalogUpsertResponse(upserted=count)


@router.post("/v1/recommend", response_model=RecommendResponse)
async def recommend_endpoint(
    request: RecommendRequest,
    tenant: Tenant = Depends(get_current_tenant),
) -> RecommendResponse:
    return await run_recommend(tenant.id, request)
