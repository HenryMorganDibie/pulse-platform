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
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str = ""
    database_url: str = "postgresql://postgres:postgres@localhost:5432/pulse_platform"
    cors_origins: str = "http://localhost:3000"

    persona_model: str = "llama-3.3-70b-versatile"
    fast_model: str = "llama-3.1-8b-instant"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
