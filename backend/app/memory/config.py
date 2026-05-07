"""Memory configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


_BACKEND_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class MemoryConfig(BaseSettings):
    """Configuration for memory services and feature flags."""

    memory_enabled: bool = False

    cognee_version: str = "1.0.5"
    graph_database_provider: str = "kuzu"
    vector_database_provider: str = "lancedb"
    enable_backend_access_control: bool = False
    memory_provider_timeout_seconds: float = 15.0

    memory_embedding_model: str = "text-embedding-3-small"
    memory_namespace_prefix: str = "task"
    memory_session_retention_seconds: int = 86400
    memory_auto_cognify_on_store: bool = True

    model_config = {
        "env_file": _BACKEND_ENV_FILE,
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_memory_config() -> MemoryConfig:
    """Return a cached memory config instance."""
    return MemoryConfig()
