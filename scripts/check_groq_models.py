"""
Pulse Platform — verify the configured Groq models are actually reachable.

Run this whenever LLM-backed responses look suspicious (generic fallback text,
identical scores across items) before assuming it's an app bug — Groq's model
catalog moves, and every LLM call in this codebase fails silently into a
named fallback rather than raising, which is good for uptime and bad for
noticing "the model was deprecated" quickly. This caught exactly that on
2026-09-08 (llama-3.3-70b-versatile / llama-3.1-8b-instant both 404'd).

Usage:
    python scripts/check_groq_models.py
"""

from __future__ import annotations

import asyncio
import sys

import httpx

sys.path.insert(0, ".")

from src.core.config import settings


async def main() -> None:
    if not settings.groq_api_key:
        print("No GROQ_API_KEY configured.")
        sys.exit(1)

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
        )

    if resp.status_code != 200:
        print(f"Could not list models: {resp.status_code} {resp.text}")
        sys.exit(1)

    available = {m["id"] for m in resp.json()["data"]}

    for label, configured in [("persona_model", settings.persona_model), ("fast_model", settings.fast_model)]:
        status = "OK" if configured in available else "MISSING — update src/core/config.py"
        print(f"{label}: {configured} — {status}")

    print("\nAll models available to this key:")
    for m in sorted(available):
        print(f"  - {m}")


if __name__ == "__main__":
    asyncio.run(main())
