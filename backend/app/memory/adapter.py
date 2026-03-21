"""Cognee-compatible adapter with graceful degradation."""

from __future__ import annotations

from typing import Any

from app.memory.config import MemoryConfig, get_memory_config
from app.utils.logger import logger


class MemoryAdapter:
    """Adapter layer for memory operations.

    This class wraps cognee-like APIs and provides a no-op fallback when
    memory is disabled or the provider is unavailable.
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

    def _resolve_client(self) -> Any | None:
        if not self.enabled:
            return None
        if self._cognee_client is not None:
            return self._cognee_client

        try:
            import cognee  # type: ignore

            self._cognee_client = cognee
            return self._cognee_client
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Memory provider unavailable, fallback to no-op: {exc}")
            return None

    async def add(
        self,
        content: str,
        *,
        namespace: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any | None:
        client = self._resolve_client()
        if client is None:
            return None

        try:
            return await client.add(
                content,
                namespace=namespace,
                metadata=metadata or {},
            )
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Memory add failed, fallback to no-op: {exc}")
            return None

    async def search(
        self,
        query: str,
        *,
        namespace: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        client = self._resolve_client()
        if client is None:
            return []

        try:
            rows = await client.search(query, namespace=namespace, top_k=limit)
            return rows or []
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Memory search failed, fallback to empty: {exc}")
            return []

    async def cognify(
        self,
        content: str,
        *,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        client = self._resolve_client()
        if client is None:
            return {}

        try:
            data = await client.cognify(content, namespace=namespace)
            return data or {}
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Memory cognify failed, fallback to empty: {exc}")
            return {}