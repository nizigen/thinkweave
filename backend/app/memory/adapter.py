"""Project-owned adapter around the installed cognee runtime."""

from __future__ import annotations

import os
from typing import Any

from app.memory.config import MemoryConfig, get_memory_config
from app.utils.logger import logger


class MemoryAdapter:
    """Adapter layer for task-scoped memory operations.

    Disabled mode preserves the v1 no-op behavior. Enabled mode must use a
    supported cognee backend matrix and surface provider failures explicitly.
    """

    def __init__(
        self,
        *,
        config: MemoryConfig | None = None,
        cognee_client: Any | None = None,
    ) -> None:
        self.config = config or get_memory_config()
        self._cognee_client = cognee_client

    @property
    def enabled(self) -> bool:
        return self.config.memory_enabled

    def ensure_supported_backend_matrix(self) -> None:
        graph = self.config.graph_database_provider
        vector = self.config.vector_database_provider

        supported_graph = {"kuzu", "falkor", "neo4j_aura_dev"}
        supported_vector = {"lancedb", "falkor", "pgvector"}

        if graph not in supported_graph or vector not in supported_vector:
            raise RuntimeError(
                f"Unsupported cognee backend combination: "
                f"graph={graph}, vector={vector}"
            )

    def _require_client(self) -> Any:
        client = self._resolve_client()
        if client is None:
            raise RuntimeError("cognee client unavailable while memory is enabled")
        return client

    def _resolve_client(self) -> Any | None:
        if not self.enabled:
            return None
        if self._cognee_client is not None:
            return self._cognee_client

        self.ensure_supported_backend_matrix()

        try:
            import cognee  # type: ignore

            os.environ.setdefault(
                "ENABLE_BACKEND_ACCESS_CONTROL",
                str(self.config.enable_backend_access_control).lower(),
            )
            self._cognee_client = cognee
            return self._cognee_client
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Memory provider unavailable in enabled mode: {exc}")
            return None

    async def add(
        self,
        content: str,
        *,
        namespace: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any | None:
        if not self.enabled:
            return None
        client = self._require_client()

        try:
            return await client.add(
                content,
                namespace=namespace,
                metadata=metadata or {},
            )
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Memory add failed in enabled mode: {exc}")
            raise

    async def search(
        self,
        query: str,
        *,
        namespace: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        client = self._require_client()

        try:
            rows = await client.search(query, namespace=namespace, top_k=limit)
            return rows or []
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Memory search failed in enabled mode: {exc}")
            raise

    async def cognify(
        self,
        content: str,
        *,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {}
        client = self._require_client()

        try:
            data = await client.cognify(content, namespace=namespace)
            return data or {}
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Memory cognify failed in enabled mode: {exc}")
            raise