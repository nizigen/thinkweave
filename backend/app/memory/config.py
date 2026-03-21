"""Memory configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class MemoryConfig(BaseSettings):
    """Configuration for memory services and feature flags."""

    memory_enabled: bool = False

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j_password"
    neo4j_database: str = "neo4j"

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "session_memory"

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