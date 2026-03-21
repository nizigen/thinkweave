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


class TestMemoryConfig:
    def test_defaults(self):
        cfg = MemoryConfig()
        assert cfg.memory_enabled is False
        assert cfg.neo4j_uri.startswith("bolt://")
        assert cfg.qdrant_url.startswith("http://")

    def test_explicit_values(self):
        cfg = MemoryConfig(
            memory_enabled=True,
            neo4j_uri="bolt://neo4j:7687",
            qdrant_url="http://qdrant:6333",
        )
        assert cfg.memory_enabled is True
        assert cfg.neo4j_uri == "bolt://neo4j:7687"
        assert cfg.qdrant_url == "http://qdrant:6333"


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
