"""
Pulse Platform — shared Groq client.

pulse-agent had this same ~40-line function copy-pasted into 4 different agent
files (persona_agent.py, review_agent.py, reasoning_agent.py, ranking_agent.py).
One copy here, imported everywhere, is the single point where a second provider
(e.g. Claude API for a future premium tier) would get added later.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqError(Exception):
    pass


async def call_groq(
    system: str,
    user: str,
    model: str,
    max_tokens: int = 400,
    temperature: float = 0.2,
) -> str:
    if not settings.groq_api_key:
        raise GroqError("Missing GROQ_API_KEY")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {settings.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
    except httpx.ConnectError as exc:
        raise GroqError("Network connection to Groq failed") from exc
    except httpx.ReadTimeout as exc:
        raise GroqError("Groq request timed out") from exc

    if response.status_code != 200:
        raise GroqError(f"{response.status_code}: {response.text}")

    return response.json()["choices"][0]["message"]["content"]


def parse_json_object(raw: str) -> Dict[str, Any]:
    """Robust parser for LLM JSON output — never raises, returns {} on failure."""
    return _parse_json(raw, open_char="{", close_char="}")


def parse_json_array(raw: str) -> list[Any]:
    result = _parse_json(raw, open_char="[", close_char="]")
    return result if isinstance(result, list) else []


def _parse_json(raw: str, open_char: str, close_char: str) -> Any:
    if not raw:
        return {} if open_char == "{" else []

    cleaned = raw.strip().replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    start = cleaned.find(open_char)
    end = cleaned.rfind(close_char)
    if start != -1 and end != -1:
        try:
            return json.loads(cleaned[start : end + 1])
        except Exception:
            pass

    pattern = r"\{[\s\S]*\}" if open_char == "{" else r"\[[\s\S]*\]"
    match = re.search(pattern, cleaned)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass

    logger.warning("LLM JSON parse failed:\n%s", raw[:300])
    return {} if open_char == "{" else []
