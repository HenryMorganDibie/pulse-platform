"""
Pulse Platform — embedding helper.

Originally called sentence-transformers locally (loads torch), which is what
pulse-agent's embedding_tool.py declared but never actually wired in — this
version wires it in for real, but as a hosted API call instead of a local
model load. torch + sentence-transformers measured at 1.1GB installed
(540MB for torch alone), far past Vercel's ~250MB serverless function bundle
limit — confirmed empirically 2026-09-08 when a local end-to-end test's
`.venv` came in at that size. Calling the same model (all-MiniLM-L6-v2) via
HuggingFace's hosted Inference API keeps the exact embedding space (no
re-embedding needed if this ever changes back) while keeping the deployed
bundle to just an httpx call.
"""

from __future__ import annotations

from typing import List

import httpx

from src.core.config import settings

_HF_ROUTER_URL = "https://router.huggingface.co/hf-inference/models/{model}/pipeline/feature-extraction"


class EmbeddingError(Exception):
    pass


async def embed_text(text: str) -> List[float]:
    if not settings.hf_api_key:
        raise EmbeddingError("Missing HF_API_KEY")

    model = settings.embedding_model.removeprefix("sentence-transformers/")
    url = _HF_ROUTER_URL.format(model=f"sentence-transformers/{model}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {settings.hf_api_key}"},
            json={"inputs": text},
        )

    if response.status_code != 200:
        raise EmbeddingError(f"HF Inference API {response.status_code}: {response.text[:300]}")

    vector = response.json()
    # A single string input returns a flat vector; guard against the
    # nested-list shape HF returns for a list input, in case that ever changes.
    if vector and isinstance(vector[0], list):
        vector = vector[0]

    return vector
