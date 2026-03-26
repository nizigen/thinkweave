"""Application settings loaded from the backend `.env` file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings


_BACKEND_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    # Database
    postgres_url: str = "postgresql+asyncpg://localhost:5432/agent_db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM providers
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    default_model: str = "gpt-4o"

    # Concurrency controls
    max_concurrent_llm_calls: int = 5
    max_concurrent_writers: int = 3

    # LLM retry policy
    llm_max_retries: int = 3
    llm_retry_base_delay: float = 1.0

    # Optional RAG
    rag_enabled: bool = False
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Application
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = False
    cors_allow_origins: str = "http://localhost:5173"
    ws_allow_query_token_fallback: bool = False
    task_auth_tokens: str = ""
    admin_user_ids: str = ""
    task_create_rate_limit_per_minute: int = 100
    disable_rate_limit: bool = False

    @field_validator("debug", mode="before")
    @classmethod
    def _normalize_debug(cls, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production", "false", "0", "off", "no"}:
                return False
            if normalized in {"debug", "dev", "development", "true", "1", "on", "yes"}:
                return True
        return value

    model_config = {
        "env_file": _BACKEND_ENV_FILE,
        "env_file_encoding": "utf-8",
    }

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allow_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
