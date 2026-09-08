"""
Pulse Platform — multi-provider LLM router.

Every LLM call in this codebase goes through `call_llm()`, which tries an
ordered list of candidates (multiple Groq models, then local Ollama as a last
resort) and fails over on timeout/rate-limit/error — same pattern as
interview-copilot's packages/ai/src/router.ts + providerHealth.ts, ported to
Python. A rate-limited or failing candidate is skipped for a cooldown window
(see provider_health.py) instead of being retried immediately, so one
exhausted model doesn't turn every subsequent request into a slow double-call.

Ollama is deliberately tried LAST, not first: a cold local model load takes
10-25s+ on this hardware (confirmed empirically — qwen3:4b actually OOMs
under current memory pressure, qwen2.5-coder:1.5b works but is slow to cold
load), unacceptable as a first-try candidate for a live HTTP request. It's
also only reachable when something is actually listening on
OLLAMA_BASE_URL (localhost by default) — once this deploys to Vercel, that
connection simply fails and the router falls through to Groq-only, which is
the intended degrade: local Ollama is a dev-time resilience boost, not a
production dependency. See CONTRACTS.md.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx

from src.core.config import settings
from src.persona.provider_health import FailureKind, ProviderHealthTracker

logger = logging.getLogger(__name__)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# gpt-oss models spend their whole token budget on internal chain-of-thought
# and return empty content unless told to reason less — confirmed 2026-09-08:
# reasoning_effort="low" cuts reasoning_tokens from 218/220 (finish_reason
# "length", empty content) down to 6/220 (finish_reason "stop", real content)
# on the exact prompts this app sends. Only sent to openai/gpt-oss-* models —
# other model families on Groq don't recognize the field.
_REASONING_EFFORT_MODELS = ("openai/gpt-oss-",)


class LLMError(Exception):
    pass


class _RateLimited(LLMError):
    pass


CallFn = Callable[[str, str, int, float], Awaitable[str]]


def _groq_call(model: str) -> CallFn:
    async def call(system: str, user: str, max_tokens: int, temperature: float) -> str:
        if not settings.groq_api_key:
            raise LLMError("Missing GROQ_API_KEY")

        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if model.startswith(_REASONING_EFFORT_MODELS):
            payload["reasoning_effort"] = "low"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    GROQ_URL,
                    headers={
                        "Authorization": f"Bearer {settings.groq_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.ConnectError as exc:
            raise LLMError("Network connection to Groq failed") from exc
        except httpx.ReadTimeout as exc:
            raise LLMError("Groq request timed out") from exc

        if response.status_code == 429:
            raise _RateLimited(f"Groq rate-limited ({model})")
        if response.status_code != 200:
            raise LLMError(f"{response.status_code}: {response.text}")

        return response.json()["choices"][0]["message"]["content"]

    return call


def _ollama_call(model: str) -> CallFn:
    async def call(system: str, user: str, max_tokens: int, temperature: float) -> str:
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(
                    f"{settings.ollama_base_url}/api/chat",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "stream": False,
                        "options": {"num_predict": max_tokens, "temperature": temperature},
                    },
                )
        except httpx.ConnectError as exc:
            raise LLMError(f"Ollama unreachable at {settings.ollama_base_url}") from exc
        except httpx.ReadTimeout as exc:
            raise LLMError("Ollama request timed out") from exc

        if response.status_code != 200:
            raise LLMError(f"{response.status_code}: {response.text}")

        return response.json()["message"]["content"]

    return call


@dataclass
class _Candidate:
    id: str
    call: CallFn


def _candidates_for_tier(tier: str) -> List[_Candidate]:
    """
    tier="persona": heavier reasoning (textual pipeline, intent extraction).
    tier="fast": high-volume per-item calls (rating, review, quality, ranking).
    Groq models are cross-fallback within a tier (if the tier's primary model
    is rate-limited, try the other tier's model before dropping to Ollama) —
    a rate limit on gpt-oss-20b doesn't have to mean both a worse-quality
    answer AND a slow local fallback in the same request.
    """
    groq_order = (
        [settings.persona_model, settings.fast_model]
        if tier == "persona"
        else [settings.fast_model, settings.persona_model]
    )
    candidates = [_Candidate(f"groq:{m}", _groq_call(m)) for m in dict.fromkeys(groq_order)]
    candidates.append(_Candidate(f"ollama:{settings.ollama_fallback_model}", _ollama_call(settings.ollama_fallback_model)))
    return candidates


_health = ProviderHealthTracker()


async def call_llm(
    system: str,
    user: str,
    tier: str = "fast",
    max_tokens: int = 400,
    temperature: float = 0.2,
) -> str:
    """
    Routes through the candidate pool for this tier, skipping any provider
    currently in cooldown, and fails over silently on error. Raises LLMError
    only if every candidate — including the local Ollama fallback — fails,
    which callers should still catch and degrade from (see products/*/agent.py
    and persona/pipelines.py: every call site here has its own named
    fallback for exactly this case).
    """
    candidates = _candidates_for_tier(tier)
    available = [c for c in candidates if _health.is_available(c.id)]
    ordered = available or candidates  # every candidate in cooldown — try anyway rather than hard-fail

    last_error: Optional[Exception] = None
    for candidate in ordered:
        try:
            content = await candidate.call(system, user, max_tokens, temperature)
            _health.record_success(candidate.id)
            return content
        except _RateLimited as exc:
            _health.record_failure(candidate.id, FailureKind.RATE_LIMIT)
            last_error = exc
            logger.warning("LLM candidate %s rate-limited, trying next", candidate.id)
        except LLMError as exc:
            _health.record_failure(candidate.id, FailureKind.ERROR)
            last_error = exc
            logger.warning("LLM candidate %s failed (%s), trying next", candidate.id, exc)

    raise LLMError(f"All LLM candidates failed for tier={tier}: {last_error}")


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
