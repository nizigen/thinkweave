"""Session-scoped memory API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.memory.adapter import MemoryAdapter
from app.memory.config import get_memory_config

if TYPE_CHECKING:
    from app.memory.knowledge.graph import KnowledgeGraph


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
        self._write_count = 0

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
        self._write_count += 1

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

    async def cleanup(
        self,
        *,
        kg: KnowledgeGraph | None = None,
        topic: str = "",
    ) -> dict[str, Any]:
        """Clean up session. If *kg* is provided and memory is enabled,
        promote high-credibility entries to the knowledge graph.

        Args:
            kg: Optional KnowledgeGraph to promote entries into.
            topic: Task topic used as query anchor for entry retrieval.
                   Falls back to task_id if not provided.
        """
        promotion_count = 0
        if kg is not None and self.adapter.enabled and self._write_count > 0:
            try:
                import hashlib
                from app.memory.knowledge.promotion import promote_session
                query_anchor = topic.strip() or self.task_id
                rows = await self.query(query_anchor, limit=20)
                entries = [
                    {
                        "key": str(
                            r.get("metadata", {}).get("node_id")
                            or r.get("id")
                            # stable hash of content as fallback — dedup-safe across runs
                            or hashlib.sha1(
                                str(r.get("content") or "").encode()
                            ).hexdigest()[:12]
                        ),
                        "content": str(r.get("content") or ""),
                        "credibility": float(r.get("metadata", {}).get("credibility", 0.75)),
                        "source_task_id": self.task_id,
                    }
                    for r in rows
                ]
                promotion_count = await promote_session(entries, kg)
            except Exception:
                from app.utils.logger import logger
                logger.opt(exception=True).warning("KG promotion failed during session cleanup")

        result = {
            "task_id": self.task_id,
            "namespace": self.namespace,
            "memory_enabled": self.adapter.enabled,
            "promotion_ready": self.adapter.enabled and self._write_count > 0,
            "write_count": self._write_count,
            "promoted_to_kg": promotion_count,
        }
        self._initialized = False
        return result
