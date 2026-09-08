"""
Pulse Platform — per-provider health tracking.

Direct port of interview-copilot's packages/ai/src/providerHealth.ts. Same
rationale: Groq's free tier meters RPM/TPM per model, so hammering a
rate-limited model in a retry loop just wastes time — better to mark it
unavailable for a cooldown window and move to the next candidate. Rate-limit
cooldowns are longer (limits reset on the order of a minute) than generic
error cooldowns (which back off exponentially in case it's a transient blip).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class FailureKind(str, Enum):
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    ERROR = "error"


BASE_COOLDOWN_S = 2.0
MAX_COOLDOWN_S = 5 * 60.0
RATE_LIMIT_COOLDOWN_S = 60.0


@dataclass
class _HealthEntry:
    consecutive_failures: int
    cooldown_until: float


class ProviderHealthTracker:
    def __init__(self) -> None:
        self._entries: Dict[str, _HealthEntry] = {}

    def is_available(self, provider_id: str, now: Optional[float] = None) -> bool:
        now = now if now is not None else time.monotonic()
        entry = self._entries.get(provider_id)
        return entry is None or now >= entry.cooldown_until

    def record_success(self, provider_id: str) -> None:
        self._entries.pop(provider_id, None)

    def record_failure(self, provider_id: str, kind: FailureKind, now: Optional[float] = None) -> None:
        now = now if now is not None else time.monotonic()
        prev = self._entries.get(provider_id)
        consecutive = (prev.consecutive_failures if prev else 0) + 1

        if kind is FailureKind.RATE_LIMIT:
            cooldown = RATE_LIMIT_COOLDOWN_S
        else:
            cooldown = min(MAX_COOLDOWN_S, BASE_COOLDOWN_S * (2 ** (consecutive - 1)))

        self._entries[provider_id] = _HealthEntry(consecutive, now + cooldown)
