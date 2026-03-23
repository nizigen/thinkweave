"""Memory configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class MemoryConfig(BaseSettings):
    """Configuration for memory services and feature flags."""

    memory_enabled: bool = False

    cognee_version: str = "0.5.5"
    graph_database_provider: str = "kuzu"
    vector_database_provider: str = "lancedb"
    enable_backend_access_control: bool = False

    memory_embedding_model: str = "text-embedding-3-small"
    memory_namespace_prefix: str = "task"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_memory_config() -> MemoryConfig:
    """Return a cached memory config instance."""
    return MemoryConfig()