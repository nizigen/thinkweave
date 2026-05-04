"""Tests for memory core infrastructure (Step 4.1b)."""

from __future__ import annotations

import pytest

from app.memory.adapter import MemoryAdapter
from app.memory.config import MemoryConfig
from app.memory.session import SessionMemory


class FakeCogneeClient:
    """Minimal async cognee-like client used for unit tests."""

    def __init__(self) -> None:
        self.add_calls: list[dict] = []
        self.search_calls: list[dict] = []
        self.cognify_calls: list[dict] = []

    async def add(self, content: str, **kwargs):
        self.add_calls.append({"content": content, **kwargs})
        return {"id": "m1"}

    async def search(self, query: str, **kwargs):
        self.search_calls.append({"query": query, **kwargs})
        return [{"content": "found", "score": 0.9}]

    async def cognify(self, content: str, **kwargs):
        self.cognify_calls.append({"content": content, **kwargs})
        return {"entities": [{"name": "Agentic Nexus"}]}


class BrokenCogneeClient:
    async def add(self, content: str, **kwargs):
        raise RuntimeError("cognee add failed")

    async def search(self, query: str, **kwargs):
        raise RuntimeError("cognee search failed")

    async def cognify(self, content: str, **kwargs):
        raise RuntimeError("cognee cognify failed")


class FakeRedis:
    def __init__(self) -> None:
        self._hashes: dict[str, dict[str, str]] = {}

    async def hset(self, key: str, mapping: dict[str, str]):
        bucket = self._hashes.setdefault(key, {})
        bucket.update(mapping)

    async def hgetall(self, key: str):
        return dict(self._hashes.get(key, {}))

    async def delete(self, *keys: str):
        for key in keys:
            self._hashes.pop(key, None)


class TestMemoryConfig:
    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("MEMORY_ENABLED", raising=False)
        monkeypatch.delenv("GRAPH_DATABASE_PROVIDER", raising=False)
        monkeypatch.delenv("VECTOR_DATABASE_PROVIDER", raising=False)
        cfg = MemoryConfig(_env_file=None)
        assert cfg.memory_enabled is False
        assert cfg.cognee_version == "0.5.5"
        assert cfg.graph_database_provider == "kuzu"
        assert cfg.vector_database_provider == "lancedb"

    def test_explicit_values(self):
        cfg = MemoryConfig(
            memory_enabled=True,
            graph_database_provider="falkor",
            vector_database_provider="pgvector",
        )
        assert cfg.memory_enabled is True
        assert cfg.graph_database_provider == "falkor"
        assert cfg.vector_database_provider == "pgvector"

    def test_default_cognee_backend_targets_match_project_architecture(self, monkeypatch):
        monkeypatch.delenv("GRAPH_DATABASE_PROVIDER", raising=False)
        monkeypatch.delenv("VECTOR_DATABASE_PROVIDER", raising=False)
        cfg = MemoryConfig(_env_file=None)

        assert cfg.graph_database_provider == "kuzu"
        assert cfg.vector_database_provider == "lancedb"


class TestMemoryAdapter:
    @pytest.mark.asyncio
    async def test_disabled_mode_noop(self):
        adapter = MemoryAdapter(
            config=MemoryConfig(memory_enabled=False),
            cognee_client=FakeCogneeClient(),
        )
        add_result = await adapter.add("hello")
        search_result = await adapter.search("hello")
        cognify_result = await adapter.cognify("hello")

        assert add_result is None
        assert search_result == []
        assert cognify_result == {}

    @pytest.mark.asyncio
    async def test_enabled_mode_calls_client(self):
        fake_client = FakeCogneeClient()
        adapter = MemoryAdapter(
            config=MemoryConfig(memory_enabled=True),
            cognee_client=fake_client,
        )
        await adapter.add("chapter summary", namespace="task-1")
        rows = await adapter.search("summary", namespace="task-1", limit=3)
        entities = await adapter.cognify("chapter summary", namespace="task-1")

        assert len(fake_client.add_calls) == 1
        assert fake_client.add_calls[0]["namespace"] == "task-1"
        assert len(rows) == 1
        assert len(fake_client.search_calls) == 1
        assert fake_client.search_calls[0]["top_k"] == 3
        assert entities["entities"][0]["name"] == "Agentic Nexus"

    @pytest.mark.asyncio
    async def test_enabled_mode_degrades_to_fallback_on_provider_failure(self):
        adapter = MemoryAdapter(
            config=MemoryConfig(memory_enabled=True),
            cognee_client=BrokenCogneeClient(),
        )

        add_result = await adapter.add("chapter summary", namespace="task-1")
        rows = await adapter.search("chapter", namespace="task-1", limit=3)

        assert adapter.degraded is True
        assert add_result is not None
        assert len(rows) == 1
        assert "chapter summary" in rows[0]["content"]

    def test_enabled_mode_rejects_unsupported_cognee_backend_matrix(self):
        adapter = MemoryAdapter(
            config=MemoryConfig(
                memory_enabled=True,
                graph_database_provider="neo4j",
                vector_database_provider="qdrant",
            ),
            cognee_client=FakeCogneeClient(),
        )

        with pytest.raises(RuntimeError, match="Unsupported cognee backend"):
            adapter.ensure_supported_backend_matrix()

    def test_runtime_backend_access_control_flag_requires_preconfigured_process(self):
        adapter = MemoryAdapter(
            config=MemoryConfig(
                memory_enabled=True,
                enable_backend_access_control=True,
            ),
            cognee_client=FakeCogneeClient(),
        )

        with pytest.raises(RuntimeError, match="process start"):
            adapter._validate_runtime_config()


class TestSessionMemory:
    @pytest.mark.asyncio
    async def test_session_lifecycle(self):
        fake_client = FakeCogneeClient()
        adapter = MemoryAdapter(
            config=MemoryConfig(memory_enabled=True),
            cognee_client=fake_client,
        )
        session = SessionMemory(task_id="task-42", adapter=adapter)

        await session.initialize()
        assert session.namespace == "task:task-42"

        await session.store("Outline draft")
        results = await session.query("Outline")
        await session.cleanup()

        assert len(results) == 1
        assert fake_client.add_calls[0]["namespace"] == "task:task-42"
        assert fake_client.search_calls[0]["namespace"] == "task:task-42"

    @pytest.mark.asyncio
    async def test_cleanup_returns_promotion_handoff_metadata(self):
        fake_client = FakeCogneeClient()
        adapter = MemoryAdapter(
            config=MemoryConfig(memory_enabled=True),
            cognee_client=fake_client,
        )
        session = SessionMemory(task_id="task-77", adapter=adapter)

        await session.initialize()
        await session.store("Outline draft", metadata={"kind": "summary"})
        cleanup_result = await session.cleanup()

        assert cleanup_result["task_id"] == "task-77"
        assert cleanup_result["namespace"] == "task:task-77"
        assert cleanup_result["memory_enabled"] is True
        assert cleanup_result["promotion_ready"] is True

    @pytest.mark.asyncio
    async def test_disabled_session_returns_empty(self):
        session = SessionMemory(
            task_id="task-99",
            adapter=MemoryAdapter(config=MemoryConfig(memory_enabled=False)),
        )
        await session.initialize()
        await session.store("x")
        rows = await session.query("x")
        await session.cleanup()
        assert rows == []

    @pytest.mark.asyncio
    async def test_snapshot_restore_and_clear_task_roundtrip(self):
        redis = FakeRedis()
        fake_client = FakeCogneeClient()
        adapter = MemoryAdapter(
            config=MemoryConfig(memory_enabled=True),
            cognee_client=fake_client,
        )

        session_a = SessionMemory(task_id="task-persist", adapter=adapter, redis_client=redis)
        await session_a.initialize()
        await session_a.store("chapter one", metadata={"chapter": 1})
        await session_a.store_territory_map("outline A")
        snap = await session_a.snapshot()

        session_b = SessionMemory(task_id="task-persist", adapter=adapter, redis_client=redis)
        await session_b.initialize()
        restored = await session_b.restore()

        assert restored["task_id"] == "task-persist"
        assert restored["dedup_registry"]
        assert restored["territory_map"]
        assert snap["snapshot_hash"] == restored["snapshot_hash"]

        await session_b.clear_task()
        empty = await session_b.restore()
        assert empty["dedup_registry"] == []
        assert empty["territory_map"] == {}

    @pytest.mark.asyncio
    async def test_restore_rejects_tampered_snapshot_hash(self):
        session = SessionMemory(
            task_id="task-hash",
            adapter=MemoryAdapter(config=MemoryConfig(memory_enabled=True), cognee_client=FakeCogneeClient()),
            redis_client=FakeRedis(),
        )
        await session.initialize()
        await session.store("content A")
        snapshot = await session.snapshot(persist=False)
        snapshot["dedup_registry"] = []

        with pytest.raises(ValueError, match="snapshot hash mismatch"):
            await session.restore(snapshot)
