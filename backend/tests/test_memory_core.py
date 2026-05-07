"""Tests for memory core infrastructure (Step 4.1b)."""

from __future__ import annotations

import asyncio
import os

import pytest

from app.config import settings
from app.memory.adapter import MemoryAdapter
from app.memory.config import MemoryConfig
from app.memory.session import SessionMemory


class FakeCogneeClient:
    """Minimal async cognee-like client used for unit tests."""

    def __init__(self) -> None:
        self.add_calls: list[dict] = []
        self.search_calls: list[dict] = []
        self.cognify_calls: list[dict] = []
        self.forget_calls: list[dict] = []

    async def add(self, content: str, **kwargs):
        self.add_calls.append({"content": content, **kwargs})
        return {"id": "m1"}

    async def search(self, query: str, **kwargs):
        self.search_calls.append({"query": query, **kwargs})
        return [{"content": "found", "score": 0.9}]

    async def cognify(self, content: str, **kwargs):
        self.cognify_calls.append({"content": content, **kwargs})
        return {"entities": [{"name": "Agentic Nexus"}]}

    async def forget(self, **kwargs):
        self.forget_calls.append(dict(kwargs))
        return {"status": "ok"}


class BrokenCogneeClient:
    async def add(self, content: str, **kwargs):
        raise RuntimeError("cognee add failed")

    async def search(self, query: str, **kwargs):
        raise RuntimeError("cognee search failed")

    async def cognify(self, content: str, **kwargs):
        raise RuntimeError("cognee cognify failed")


class SlowCogneeClient:
    async def add(self, content: str, **kwargs):
        await asyncio.sleep(1.2)
        return {"id": "slow-1"}

    async def search(self, query: str, **kwargs):
        await asyncio.sleep(1.2)
        return [{"content": "slow"}]

    async def cognify(self, content: str, **kwargs):
        await asyncio.sleep(1.2)
        return {"entities": [{"name": "slow"}]}


class EmptySearchCogneeClient(FakeCogneeClient):
    async def search(self, query: str, **kwargs):
        self.search_calls.append({"query": query, **kwargs})
        return []


class FakeRedis:
    def __init__(self) -> None:
        self._hashes: dict[str, dict[str, str]] = {}
        self._zsets: dict[str, dict[str, float]] = {}
        self._ttl: dict[str, int] = {}

    async def hset(self, key: str, mapping: dict[str, str]):
        bucket = self._hashes.setdefault(key, {})
        bucket.update(mapping)

    async def hgetall(self, key: str):
        return dict(self._hashes.get(key, {}))

    async def delete(self, *keys: str):
        for key in keys:
            self._hashes.pop(key, None)
            self._zsets.pop(key, None)
            self._ttl.pop(key, None)

    async def expire(self, key: str, seconds: int):
        self._ttl[key] = int(seconds)

    async def zadd(self, key: str, mapping: dict[str, float]):
        bucket = self._zsets.setdefault(key, {})
        for member, score in mapping.items():
            bucket[str(member)] = float(score)

    async def zrangebyscore(self, key: str, min_score: float, max_score: float):
        bucket = self._zsets.get(key, {})
        out = [
            member
            for member, score in bucket.items()
            if float(min_score) <= float(score) <= float(max_score)
        ]
        out.sort()
        return out

    async def zrem(self, key: str, member: str):
        bucket = self._zsets.get(key, {})
        bucket.pop(str(member), None)


class TestMemoryConfig:
    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("MEMORY_ENABLED", raising=False)
        monkeypatch.delenv("GRAPH_DATABASE_PROVIDER", raising=False)
        monkeypatch.delenv("VECTOR_DATABASE_PROVIDER", raising=False)
        cfg = MemoryConfig(_env_file=None)
        assert cfg.memory_enabled is False
        assert cfg.cognee_version == "1.0.5"
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
    def test_prime_cognee_env_bridges_backend_settings(self, monkeypatch):
        for key in (
            "LLM_PROVIDER",
            "LLM_MODEL",
            "LLM_ENDPOINT",
            "LLM_API_KEY",
            "GRAPH_DATABASE_PROVIDER",
            "VECTOR_DB_PROVIDER",
            "VECTOR_DATASET_DATABASE_HANDLER",
            "DB_PROVIDER",
            "DB_HOST",
            "DB_PORT",
            "DB_NAME",
            "DB_USERNAME",
            "DB_PASSWORD",
        ):
            monkeypatch.delenv(key, raising=False)

        monkeypatch.setattr(settings, "openrouter_api_key", "sk-test-openrouter")
        monkeypatch.setattr(settings, "openrouter_base_url", "https://openrouter.ai/api/v1")
        monkeypatch.setattr(settings, "default_model", "deepseek-v3.2")
        monkeypatch.setattr(
            settings,
            "postgres_url",
            "postgresql+asyncpg://agent_user:agent_pass@localhost:15432/agent_db",
        )

        adapter = MemoryAdapter(
            config=MemoryConfig(
                memory_enabled=True,
                graph_database_provider="kuzu",
                vector_database_provider="pgvector",
            ),
            cognee_client=FakeCogneeClient(),
        )

        adapter._prime_cognee_env()

        assert os.environ["LLM_PROVIDER"] == "openai"
        assert os.environ["LLM_MODEL"] == "deepseek/deepseek-v3.2"
        assert os.environ["LLM_ENDPOINT"] == "https://openrouter.ai/api/v1"
        assert os.environ["LLM_API_KEY"] == "sk-test-openrouter"
        assert os.environ["GRAPH_DATABASE_PROVIDER"] == "kuzu"
        assert os.environ["VECTOR_DB_PROVIDER"] == "pgvector"
        assert os.environ["VECTOR_DATASET_DATABASE_HANDLER"] == "pgvector"
        assert os.environ["DB_PROVIDER"] == "postgres"
        assert os.environ["DB_HOST"] == "localhost"
        assert os.environ["DB_PORT"] == "15432"
        assert os.environ["DB_NAME"] == "agent_db"
        assert os.environ["DB_USERNAME"] == "agent_user"
        assert os.environ["DB_PASSWORD"] == "agent_pass"

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

    @pytest.mark.asyncio
    async def test_enabled_mode_degrades_to_fallback_on_provider_timeout(self):
        adapter = MemoryAdapter(
            config=MemoryConfig(memory_enabled=True, memory_provider_timeout_seconds=1),
            cognee_client=SlowCogneeClient(),
        )

        add_result = await adapter.add("timeout summary", namespace="task-timeout")
        rows = await adapter.search("timeout", namespace="task-timeout", limit=3)
        entities = await adapter.cognify("timeout summary", namespace="task-timeout")

        assert adapter.degraded is True
        assert add_result is not None
        assert rows
        assert entities.get("entities")

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
        session = SessionMemory(task_id="task-42", adapter=adapter, redis_client=FakeRedis())

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
        session = SessionMemory(task_id="task-77", adapter=adapter, redis_client=FakeRedis())

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
            redis_client=FakeRedis(),
        )
        await session.initialize()
        await session.store("x")
        rows = await session.query("x")
        await session.cleanup()
        assert rows == []

    @pytest.mark.asyncio
    async def test_query_falls_back_to_session_summary_cache_when_search_empty(self):
        adapter = MemoryAdapter(
            config=MemoryConfig(memory_enabled=True),
            cognee_client=EmptySearchCogneeClient(),
        )
        session = SessionMemory(task_id="task-summary-fallback", adapter=adapter, redis_client=FakeRedis())
        await session.initialize()
        await session.store(
            "MVP 定义与增长飞轮必须保持术语一致，避免在章节间切换同义词。",
            metadata={"role": "writer", "chapter_title": "术语规范"},
        )

        rows = await session.query("术语一致", limit=3)

        assert rows
        assert rows[0]["source"] == "session_summary_cache"
        assert "术语一致" in rows[0]["content"]

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

    @pytest.mark.asyncio
    async def test_cleanup_with_zero_retention_forgets_dataset_immediately(self):
        fake_client = FakeCogneeClient()
        adapter = MemoryAdapter(
            config=MemoryConfig(
                memory_enabled=True,
                memory_session_retention_seconds=0,
            ),
            cognee_client=fake_client,
        )
        session = SessionMemory(task_id="task-zero-retention", adapter=adapter, redis_client=FakeRedis())

        await session.initialize()
        await session.store("transient content")
        result = await session.cleanup()

        assert result["retention_seconds"] == 0
        assert fake_client.forget_calls
        assert fake_client.forget_calls[0]["dataset"] == "task_task-zero-retention"

    @pytest.mark.asyncio
    async def test_cleanup_with_positive_retention_schedules_deletion(self):
        fake_client = FakeCogneeClient()
        redis = FakeRedis()
        adapter = MemoryAdapter(
            config=MemoryConfig(
                memory_enabled=True,
                memory_session_retention_seconds=300,
            ),
            cognee_client=fake_client,
        )
        session = SessionMemory(task_id="task-retained", adapter=adapter, redis_client=redis)

        await session.initialize()
        await session.store("retain briefly")
        result = await session.cleanup()

        assert result["retention_seconds"] == 300
        assert not fake_client.forget_calls
        assert "session_memory:retention:datasets" in redis._zsets
