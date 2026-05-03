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
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    default_model: str = "deepseek-v3.2"

    # Concurrency controls
    max_concurrent_llm_calls: int = 5
    max_concurrent_writers: int = 3
    enable_planned_expansion_nodes: bool = False
    enable_finalize_auto_expansion: bool = False

    # LLM retry policy
    llm_max_retries: int = 3
    llm_retry_base_delay: float = 1.0
    llm_request_timeout_seconds: int = 120

    # DAG node timeout controls (seconds)
    dag_node_timeout_seconds: int = 300
    dag_writer_node_timeout_seconds: int = 180

    # Optional RAG
    rag_enabled: bool = False
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Application
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = False
    cors_allow_origins: str = (
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "http://localhost:4173,"
        "http://127.0.0.1:4173"
    )
    ws_allow_query_token_fallback: bool = False
    task_auth_tokens: str = ""
    admin_user_ids: str = ""
    task_create_rate_limit_per_minute: int = 100
    disable_rate_limit: bool = False
    mock_llm_enabled: bool = False
    frontend_dist_dir: str = ""

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
        "extra": "ignore",
    }

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allow_origins.split(",")
            if origin.strip()
        ]


settings = Settings()


def resolve_model_choice(
    model: str | None,
    custom_model: str | None,
    default_model: str,
) -> str:
    """Resolve the stored model name from optional predefined/custom inputs."""
    custom = str(custom_model or "").strip()
    if custom:
        return custom
    selected = str(model or "").strip()
    if selected:
        return selected
    fallback = str(default_model or "").strip()
    return fallback or settings.default_model


def available_model_options(extra_models: list[str] | None = None) -> list[dict[str, str]]:
    """Return selectable model options for the agent management UI."""
    known_models = [
        settings.default_model,
        "deepseek-v3.2",
        "deepseek-chat",
    ]
    if extra_models:
        known_models.extend(extra_models)

    options: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_name in known_models:
        name = str(raw_name or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        provider = "deepseek" if name.startswith("deepseek") else "openai"
        options.append(
            {
                "value": name,
                "label": name,
                "description": "",
                "provider": provider,
            }
        )
    return options
