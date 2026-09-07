"""
Pulse Platform — embedding helper.

This is the piece pulse-agent never actually wired in: it declared
sentence-transformers as a dependency and named a model in config.yaml, but
src/tools/embedding_tool.py was never imported by anything, and retrieval ran
on keyword-token overlap instead. Here, embeddings are computed on every
catalog upsert and every recommend query, and similarity search happens in
Postgres via pgvector (see migrations/001_init.sql, catalog_items.embedding).

The model loads once per process (it's ~80MB, CPU-friendly) and `encode()` is
blocking, so it runs off the event loop via asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, List

from src.core.config import settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

_model: "SentenceTransformer | None" = None


def _get_model() -> "SentenceTransformer":
    # Imported lazily so modules that only need retrieve_candidates' types
    # (or that mock this function out in tests) don't have to pull in torch.
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(settings.embedding_model)
    return _model


def _encode(text: str) -> List[float]:
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


async def embed_text(text: str) -> List[float]:
    return await asyncio.to_thread(_encode, text)
