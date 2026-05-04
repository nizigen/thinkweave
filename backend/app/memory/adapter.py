"""Project-owned adapter around memory backends with cognee fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.memory.config import MemoryConfig, get_memory_config
from app.utils.logger import logger


@dataclass
class _InMemoryBackend:
    """Lightweight in-process fallback backend."""

    _store: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    async def add(
        self,
        content: str,
        *,
        namespace: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ns = str(namespace or "")
        bucket = self._store.setdefault(ns, [])
        item = {
            "id": f"inmem-{len(bucket) + 1}",
            "content": content,
            "metadata": dict(metadata or {}),
        }
        bucket.append(item)
        return {"id": item["id"]}

    async def search(
        self,
        query: str,
        *,
        namespace: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        ns = str(namespace or "")
        rows = list(self._store.get(ns, []))
        q = str(query or "").strip().lower()
        if not q:
            return rows[: max(0, int(top_k))]

        matched = [
            row
            for row in rows
            if q in str(row.get("content", "")).lower()
        ]
        return matched[: max(0, int(top_k))]

    async def cognify(
        self,
        content: str,
        *,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        text = str(content or "").strip()
        if not text:
            return {}
        return {
            "entities": [
                {
                    "name": text[:48],
                    "source": str(namespace or ""),
                }
            ]
        }


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
        self._fallback_backend = _InMemoryBackend()
        self._degraded = False

    @property
    def enabled(self) -> bool:
        return self.config.memory_enabled

    @property
    def degraded(self) -> bool:
        return self._degraded

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

    def _validate_runtime_config(self) -> None:
        if self.config.enable_backend_access_control:
            raise RuntimeError(
                "enable_backend_access_control must be configured before process "
                "start; MemoryAdapter does not mutate provider runtime config"
            )

    def _resolve_client(self) -> Any | None:
        if not self.enabled:
            return None
        if self._cognee_client is not None:
            return self._cognee_client

        self.ensure_supported_backend_matrix()
        self._validate_runtime_config()

        try:
            import cognee  # type: ignore

            self._cognee_client = cognee
            return self._cognee_client
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Memory provider unavailable in enabled mode: {exc}")
            return None

    def _degrade_to_fallback(self, *, reason: str) -> None:
        if not self._degraded:
            logger.warning("Memory adapter degraded to fallback backend: {}", reason)
        self._degraded = True

    async def add(
        self,
        content: str,
        *,
        namespace: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any | None:
        if not self.enabled:
            return None
        client = self._resolve_client()
        if client is None:
            self._degrade_to_fallback(reason="cognee client unavailable")
            return await self._fallback_backend.add(
                content,
                namespace=namespace,
                metadata=metadata or {},
            )

        try:
            return await client.add(
                content,
                namespace=namespace,
                metadata=metadata or {},
            )
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Memory add failed in enabled mode: {exc}")
            self._degrade_to_fallback(reason=f"add failed: {exc}")
            return await self._fallback_backend.add(
                content,
                namespace=namespace,
                metadata=metadata or {},
            )

    async def search(
        self,
        query: str,
        *,
        namespace: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        client = self._resolve_client()
        if client is None:
            self._degrade_to_fallback(reason="cognee client unavailable")
            return await self._fallback_backend.search(
                query,
                namespace=namespace,
                top_k=limit,
            )

        try:
            rows = await client.search(query, namespace=namespace, top_k=limit)
            return rows or []
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Memory search failed in enabled mode: {exc}")
            self._degrade_to_fallback(reason=f"search failed: {exc}")
            return await self._fallback_backend.search(
                query,
                namespace=namespace,
                top_k=limit,
            )

    async def cognify(
        self,
        content: str,
        *,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {}
        client = self._resolve_client()
        if client is None:
            self._degrade_to_fallback(reason="cognee client unavailable")
            return await self._fallback_backend.cognify(
                content,
                namespace=namespace,
            )

        try:
            data = await client.cognify(content, namespace=namespace)
            return data or {}
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Memory cognify failed in enabled mode: {exc}")
            self._degrade_to_fallback(reason=f"cognify failed: {exc}")
            return await self._fallback_backend.cognify(
                content,
                namespace=namespace,
            )
