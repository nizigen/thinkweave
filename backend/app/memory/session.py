"""Session-scoped memory API with optional Redis-backed persistence."""

from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING, Any

from app.memory.adapter import MemoryAdapter
from app.memory.config import get_memory_config
from app.redis_client import get_redis
from app.utils.logger import logger

if TYPE_CHECKING:
    from app.memory.knowledge.graph import KnowledgeGraph


SESSION_SNAPSHOT_SCHEMA_VERSION = "session-memory:v1"
SESSION_RETENTION_SCHEDULE_KEY = "session_memory:retention:datasets"


class SessionMemory:
    """Unified session memory API for one task."""

    def __init__(
        self,
        *,
        task_id: str,
        adapter: MemoryAdapter | None = None,
        redis_client: Any | None = None,
    ) -> None:
        self.task_id = task_id
        self.adapter = adapter or MemoryAdapter(config=get_memory_config())
        self.namespace = ""
        self._initialized = False
        self._write_count = 0
        self._restored = False
        self._redis_client = redis_client
        self._dedup_cache: set[str] = set()
        self._territory_cache: dict[str, Any] = {}
        self._summary_cache: dict[str, Any] = {}
        self._cognified_once = False

    async def initialize(self) -> bool:
        self.namespace = (
            f"{self.adapter.config.memory_namespace_prefix}:{self.task_id}"
        )
        self._initialized = True
        if self.adapter.enabled and not self._restored:
            await self.restore()
        if self.adapter.enabled:
            await self._run_retention_maintenance()
        return self.adapter.enabled

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()

    @property
    def _dedup_key(self) -> str:
        return f"session:{self.task_id}:dedup"

    @property
    def _territory_key(self) -> str:
        return f"session:{self.task_id}:territory"

    @property
    def _summary_key(self) -> str:
        return f"session:{self.task_id}:summary"

    async def _get_redis(self) -> Any | None:
        if not self.adapter.enabled:
            return None
        if self._redis_client is not None:
            return self._redis_client
        try:
            return await get_redis()
        except Exception:
            logger.opt(exception=True).warning("session memory redis client unavailable")
            return None

    @staticmethod
    def _supports_redis_command(client: Any, name: str) -> bool:
        return hasattr(client, name)

    def _retention_seconds(self) -> int:
        try:
            value = int(getattr(self.adapter.config, "memory_session_retention_seconds", 0))
        except Exception:
            value = 0
        return max(0, value)

    async def _expire_snapshot_keys(self, *, retention_seconds: int) -> None:
        if retention_seconds <= 0:
            return
        client = await self._get_redis()
        if client is None:
            return
        if not self._supports_redis_command(client, "expire"):
            return
        try:
            await client.expire(self._dedup_key, retention_seconds)
            await client.expire(self._territory_key, retention_seconds)
            await client.expire(self._summary_key, retention_seconds)
        except Exception:
            logger.opt(exception=True).warning("failed to set session memory redis ttl")

    async def _schedule_dataset_cleanup(self, *, retention_seconds: int) -> None:
        if retention_seconds <= 0:
            return
        client = await self._get_redis()
        if client is None:
            return
        if not self._supports_redis_command(client, "zadd"):
            return
        dataset_name = self.adapter._namespace_to_dataset(self.namespace)
        run_at = float(time.time()) + float(retention_seconds)
        payload = json.dumps(
            {
                "task_id": self.task_id,
                "namespace": self.namespace,
                "dataset": dataset_name,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        try:
            await client.zadd(SESSION_RETENTION_SCHEDULE_KEY, {payload: run_at})
        except Exception:
            logger.opt(exception=True).warning("failed to enqueue session memory cleanup")

    async def _run_retention_maintenance(self) -> None:
        client = await self._get_redis()
        if client is None:
            return
        if not self._supports_redis_command(client, "zrangebyscore"):
            return

        now = float(time.time())
        try:
            due = await client.zrangebyscore(SESSION_RETENTION_SCHEDULE_KEY, 0, now)
        except Exception:
            return

        for raw in due or []:
            payload = str(raw or "").strip()
            if not payload:
                continue

            task_id = ""
            namespace = ""
            dataset = ""
            try:
                record = json.loads(payload)
                if isinstance(record, dict):
                    task_id = str(record.get("task_id") or "").strip()
                    namespace = str(record.get("namespace") or "").strip()
                    dataset = str(record.get("dataset") or "").strip()
            except Exception:
                dataset = payload

            target = dataset or namespace
            if target:
                await self.adapter.forget_dataset(target)

            if task_id and self._supports_redis_command(client, "delete"):
                try:
                    await client.delete(
                        f"session:{task_id}:dedup",
                        f"session:{task_id}:territory",
                        f"session:{task_id}:summary",
                    )
                except Exception:
                    logger.opt(exception=True).warning("failed to delete retained session keys")

            if self._supports_redis_command(client, "zrem"):
                try:
                    await client.zrem(SESSION_RETENTION_SCHEDULE_KEY, payload)
                except Exception:
                    pass

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(str(content or "").encode("utf-8")).hexdigest()

    @staticmethod
    def _compute_snapshot_hash(payload: dict[str, Any]) -> str:
        basis = {
            "schema_version": payload.get("schema_version"),
            "task_id": payload.get("task_id"),
            "dedup_registry": sorted(payload.get("dedup_registry", [])),
            "territory_map": payload.get("territory_map", {}),
            "summary_map": payload.get("summary_map", {}),
        }
        raw = json.dumps(basis, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _clear_local_cache(self) -> None:
        self._dedup_cache.clear()
        self._territory_cache.clear()
        self._summary_cache.clear()
        self._restored = False
        self._write_count = 0

    async def _persist_snapshot_to_redis(self, payload: dict[str, Any]) -> None:
        client = await self._get_redis()
        if client is None:
            return

        dedup_map = {item: "1" for item in payload.get("dedup_registry", [])}
        territory_map = {
            str(key): json.dumps(value, ensure_ascii=False)
            for key, value in payload.get("territory_map", {}).items()
        }
        summary_map = {
            str(key): json.dumps(value, ensure_ascii=False)
            for key, value in payload.get("summary_map", {}).items()
        }
        summary_map["_meta_schema_version"] = str(payload.get("schema_version", ""))
        summary_map["_meta_snapshot_hash"] = str(payload.get("snapshot_hash", ""))

        try:
            await client.delete(self._dedup_key, self._territory_key, self._summary_key)
            if dedup_map:
                await client.hset(self._dedup_key, mapping=dedup_map)
            if territory_map:
                await client.hset(self._territory_key, mapping=territory_map)
            if summary_map:
                await client.hset(self._summary_key, mapping=summary_map)
        except Exception:
            logger.opt(exception=True).warning("failed to persist session snapshot")

    async def snapshot(self, *, persist: bool = True) -> dict[str, Any]:
        await self._ensure_initialized()
        payload = {
            "schema_version": SESSION_SNAPSHOT_SCHEMA_VERSION,
            "task_id": self.task_id,
            "dedup_registry": sorted(self._dedup_cache),
            "territory_map": dict(self._territory_cache),
            "summary_map": dict(self._summary_cache),
        }
        payload["snapshot_hash"] = self._compute_snapshot_hash(payload)
        if persist and self.adapter.enabled:
            await self._persist_snapshot_to_redis(payload)
        return payload

    async def restore(self, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        await self._ensure_initialized()

        if not self.adapter.enabled:
            self._restored = True
            return await self.snapshot(persist=False)

        if snapshot is not None:
            expected_hash = str(snapshot.get("snapshot_hash") or "").strip()
            if expected_hash:
                actual_hash = self._compute_snapshot_hash(snapshot)
                if expected_hash != actual_hash:
                    raise ValueError("SessionMemory snapshot hash mismatch")
            self._dedup_cache = {
                str(item).strip()
                for item in snapshot.get("dedup_registry", [])
                if str(item).strip()
            }
            territory = snapshot.get("territory_map", {})
            summary = snapshot.get("summary_map", {})
            self._territory_cache = territory if isinstance(territory, dict) else {}
            self._summary_cache = summary if isinstance(summary, dict) else {}
            self._restored = True
            return await self.snapshot(persist=False)

        client = await self._get_redis()
        if client is None:
            self._restored = True
            return await self.snapshot(persist=False)

        try:
            dedup_raw = await client.hgetall(self._dedup_key)
            territory_raw = await client.hgetall(self._territory_key)
            summary_raw = await client.hgetall(self._summary_key)
        except Exception:
            logger.opt(exception=True).warning("failed to restore session memory from redis")
            self._restored = True
            return await self.snapshot(persist=False)

        self._dedup_cache = {
            str(key).strip()
            for key in (dedup_raw or {}).keys()
            if str(key).strip()
        }
        parsed_territory: dict[str, Any] = {}
        for key, raw in (territory_raw or {}).items():
            try:
                parsed_territory[str(key)] = json.loads(str(raw))
            except Exception:
                parsed_territory[str(key)] = raw
        parsed_summary: dict[str, Any] = {}
        for key, raw in (summary_raw or {}).items():
            if str(key).startswith("_meta_"):
                continue
            try:
                parsed_summary[str(key)] = json.loads(str(raw))
            except Exception:
                parsed_summary[str(key)] = raw
        self._territory_cache = parsed_territory
        self._summary_cache = parsed_summary
        self._restored = True
        return await self.snapshot(persist=False)

    async def clear_task(self) -> None:
        await self._ensure_initialized()
        self._clear_local_cache()
        client = await self._get_redis()
        if client is None:
            return
        try:
            await client.delete(self._dedup_key, self._territory_key, self._summary_key)
        except Exception:
            logger.opt(exception=True).warning("failed to clear session memory redis keys")

    async def store(
        self,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._ensure_initialized()
        digest = self._content_hash(content)
        if digest in self._dedup_cache:
            return

        await self.adapter.add(
            content,
            namespace=self.namespace,
            metadata=metadata,
        )
        if self.adapter.enabled and not self._cognified_once:
            auto_cognify = bool(
                getattr(self.adapter.config, "memory_auto_cognify_on_store", True)
            )
            if auto_cognify:
                try:
                    await self.adapter.cognify(content, namespace=self.namespace)
                    self._cognified_once = True
                except Exception:
                    logger.opt(exception=True).warning("session memory auto-cognify failed")
        self._dedup_cache.add(digest)
        self._summary_cache[digest] = {
            "summary": str(content or "")[:500],
            "metadata": dict(metadata or {}),
        }
        self._write_count += 1

        if self.adapter.enabled:
            await self._persist_snapshot_to_redis(await self.snapshot(persist=False))

    async def query(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        def _summary_fallback_rows(query_text: str, take: int) -> list[dict[str, Any]]:
            if take <= 0 or not self._summary_cache:
                return []

            normalized_query = str(query_text or "").strip().lower()
            values = list(self._summary_cache.values())
            selected: list[dict[str, Any]] = []

            for row in reversed(values):
                if not isinstance(row, dict):
                    continue
                summary = str(row.get("summary", "")).strip()
                metadata = row.get("metadata", {})
                metadata_dict = metadata if isinstance(metadata, dict) else {}
                if not summary:
                    continue

                if normalized_query:
                    haystack = " ".join(
                        str(item or "")
                        for item in (
                            summary,
                            metadata_dict.get("title", ""),
                            metadata_dict.get("chapter_title", ""),
                            metadata_dict.get("role", ""),
                        )
                    ).lower()
                    if normalized_query not in haystack:
                        continue

                selected.append(
                    {
                        "content": summary,
                        "metadata": metadata_dict,
                        "score": 0.01,
                        "source": "session_summary_cache",
                    }
                )
                if len(selected) >= take:
                    break

            if selected:
                return selected

            for row in reversed(values):
                if not isinstance(row, dict):
                    continue
                summary = str(row.get("summary", "")).strip()
                if not summary:
                    continue
                metadata = row.get("metadata", {})
                metadata_dict = metadata if isinstance(metadata, dict) else {}
                selected.append(
                    {
                        "content": summary,
                        "metadata": metadata_dict,
                        "score": 0.01,
                        "source": "session_summary_cache",
                    }
                )
                if len(selected) >= take:
                    break
            return selected

        await self._ensure_initialized()
        rows = await self.adapter.search(
            query,
            namespace=self.namespace,
            limit=limit,
        )
        if rows:
            return rows

        if (
            self.adapter.enabled
            and self._write_count > 0
            and not self._cognified_once
        ):
            try:
                await self.adapter.cognify(query, namespace=self.namespace)
                self._cognified_once = True
                rows = await self.adapter.search(
                    query,
                    namespace=self.namespace,
                    limit=limit,
                )
            except Exception:
                logger.opt(exception=True).warning("session memory query recovery cognify failed")
        if rows:
            return rows
        if self.adapter.enabled and self._summary_cache:
            return _summary_fallback_rows(query, limit)
        return rows

    async def store_territory_map(self, content: str) -> dict[str, Any]:
        await self._ensure_initialized()
        result = await self.adapter.cognify(content, namespace=self.namespace)
        marker = hashlib.sha1(str(content or "").encode("utf-8")).hexdigest()[:12]
        self._territory_cache[marker] = result or {}
        if self.adapter.enabled:
            await self._persist_snapshot_to_redis(await self.snapshot(persist=False))
        return result

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
                from app.memory.knowledge.promotion import promote_session

                query_anchor = topic.strip() or self.task_id
                rows = await self.query(query_anchor, limit=20)
                entries = [
                    {
                        "key": str(
                            (
                                r.get("metadata", {})
                                if isinstance(r.get("metadata"), dict)
                                else {}
                            ).get("node_id")
                            or r.get("id")
                            or hashlib.sha1(
                                str(r.get("content") or "").encode()
                            ).hexdigest()[:12]
                        ),
                        "content": str(r.get("content") or ""),
                        "credibility": float(
                            (
                                r.get("metadata", {})
                                if isinstance(r.get("metadata"), dict)
                                else {}
                            ).get("credibility", 0.75)
                        ),
                        "source_task_id": self.task_id,
                    }
                    for r in rows
                ]
                promotion_count = await promote_session(entries, kg)
            except Exception:
                logger.opt(exception=True).warning("KG promotion failed during session cleanup")

        result = {
            "task_id": self.task_id,
            "namespace": self.namespace,
            "memory_enabled": self.adapter.enabled,
            "promotion_ready": self.adapter.enabled and self._write_count > 0,
            "write_count": self._write_count,
            "promoted_to_kg": promotion_count,
        }
        retention_seconds = self._retention_seconds()
        result["retention_seconds"] = retention_seconds

        if self.adapter.enabled:
            if retention_seconds > 0:
                await self._schedule_dataset_cleanup(retention_seconds=retention_seconds)
                await self._expire_snapshot_keys(retention_seconds=retention_seconds)
            else:
                await self.adapter.forget_dataset(self.namespace)
                await self.clear_task()
        else:
            await self.clear_task()

        self._clear_local_cache()
        self._initialized = False
        return result
