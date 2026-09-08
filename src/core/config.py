"""
Pulse Platform — settings.

Every value here is read from the environment. Nothing is hardcoded and nothing
claims a provider or model the code doesn't actually call — see pulse-agent's
configs/config.yaml for the failure mode this is avoiding (it named
llm_provider: anthropic while every agent hardcoded Groq).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env.local is written by `neon link` (npx neon@latest link) and takes
    # precedence — it's the live pooled connection string for whichever
    # Neon project/branch this repo is currently linked to.
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")

    groq_api_key: str = ""
    hf_api_key: str = ""
    database_url: str = "postgresql://postgres:postgres@localhost:5432/pulse_platform"
    cors_origins: str = "http://localhost:3000"

    # Groq's catalog moves — llama-3.3-70b-versatile / llama-3.1-8b-instant
    # (pulse-agent's original choices) were both 404 model_not_found as of
    # 2026-09-08. Current larger/faster pair on this account. If either
    # starts 404ing again, check `GET /openai/v1/models` (see
    # scripts/check_groq_models.py) rather than guessing a new ID.
    persona_model: str = "openai/gpt-oss-120b"
    fast_model: str = "openai/gpt-oss-20b"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # Last-resort fallback when every Groq candidate is rate-limited/down.
    # Only reachable in local dev (see persona/llm.py) — a deployed instance
    # simply fails to connect and falls through to Groq-only. 1.5b specifically
    # because it's the largest model that reliably loads under this laptop's
    # actual memory pressure — qwen3:4b OOMs, qwen2.5-coder:3b times out cold
    # loading — confirmed empirically 2026-09-08, not a guess.
    ollama_base_url: str = "http://localhost:11434"
    ollama_fallback_model: str = "qwen2.5-coder:1.5b"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
