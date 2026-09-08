"""
Pulse Platform — FastAPI app.

Run locally:
    uvicorn src.main:app --reload --port 8000

Then visit: http://localhost:8000/docs
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.core.db import close_pool, init_pool
from src.persona.router import router as subjects_router
from src.products.recommend.router import router as recommend_router
from src.products.simulate.router import router as simulate_router
from src.schemas.api import HealthResponse

# Every LLM call in this codebase deliberately falls back to named default
# text/scores instead of raising (see persona/pipelines.py, products/*/agent.py,
# ranking.py) — good for uptime, bad for noticing a total model failure. That
# only works if the WARNING-level "X fallback used" logs it emits are actually
# visible. Uvicorn's own access logs show regardless, but this app's loggers
# are silent below root's default (WARNING-and-up *is* the default, but only
# once something has actually called basicConfig — without it, library
# loggers with no configured handler drop everything). Explicit here so a
# silently-deprecated model (this bit once — see scripts/check_groq_models.py)
# shows up as a log line instead of a plausible-looking 200 OK.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(
    title="Pulse Platform API",
    description=(
        "Persona-conditioned review simulation (flagship product) and "
        "recommendation (secondary product) over one persisted, multi-tenant "
        "user-persona core."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(subjects_router)
app.include_router(simulate_router)
app.include_router(recommend_router)


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")
