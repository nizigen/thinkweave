"""Session-scoped memory API."""

from __future__ import annotations

from typing import Any

from app.memory.adapter import MemoryAdapter
from app.memory.config import get_memory_config


class SessionMemory:
    """Unified session memory API for one task."""

    def __init__(
        self,
        *,
        task_id: str,
        adapter: MemoryAdapter | None = None,
    ) -> None:
        self.task_id = task_id
        self.adapter = adapter or MemoryAdapter(config=get_memory_config())
        self.namespace = ""
        self._initialized = False

    async def initialize(self) -> bool:
        self.namespace = (
            f"{self.adapter.config.memory_namespace_prefix}:{self.task_id}"
        )
        self._initialized = True
        return self.adapter.enabled

    async def store(
        self,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self._initialized:
            await self.initialize()
        await self.adapter.add(
            content,
            namespace=self.namespace,
            metadata=metadata,
        )

    async def query(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        if not self._initialized:
            await self.initialize()
        return await self.adapter.search(
            query,
            namespace=self.namespace,
            limit=limit,
        )

    async def store_territory_map(self, content: str) -> dict[str, Any]:
        if not self._initialized:
            await self.initialize()
        return await self.adapter.cognify(content, namespace=self.namespace)

    async def cleanup(self) -> None:
        self._initialized = False
