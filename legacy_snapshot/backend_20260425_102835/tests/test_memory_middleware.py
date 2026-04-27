"""Tests for memory middleware integration in agent pipeline."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.agents.base_agent import BaseAgent
from app.agents.middleware import MemoryMiddleware


class _DummyLLM:
    async def chat(self, *args, **kwargs):
        return "ok"


class _SimpleAgent(BaseAgent):
    async def handle_task(self, ctx: dict[str, Any]) -> str:
        return "result"


class _StubSessionDisabled:
    def __init__(self):
        self.store_calls = 0

    async def initialize(self):
        return False

    async def query(self, query: str, limit: int = 5):
        return []

    async def store(self, content: str, metadata=None):
        self.store_calls += 1
        return None

    async def store_territory_map(self, content: str):
        return {}


class _StubSessionEnabled:
    def __init__(self):
        self.stored: list[tuple[str, dict[str, Any] | None]] = []
        self.territory_calls = 0
        self.queries: list[tuple[str, int]] = []

    async def initialize(self):
        return True

    async def query(self, query: str, limit: int = 5):
        self.queries.append((query, limit))
        return [{"content": "existing context"}]

    async def store(self, content: str, metadata=None):
        self.stored.append((content, metadata))
        return None

    async def store_territory_map(self, content: str):
        self.territory_calls += 1
        return {"stored": True}


@pytest.mark.asyncio
async def test_memory_middleware_disabled_mode_sets_empty_memory_context():
    stub = _StubSessionDisabled()
    mw = MemoryMiddleware(session_factory=lambda _tid: stub)
    agent = _SimpleAgent(
        agent_id=uuid.uuid4(),
        name="test",
        role="writer",
        layer=2,
        llm_client=_DummyLLM(),
        middlewares=(),
    )
    ctx = {"task_id": "t1", "title": "chapter one"}
    result = await mw.before_task(agent, ctx)
    assert result["memory_context"] == ""

    after = await mw.after_task(agent, result, "ignored result")
    assert after == "ignored result"
    assert stub.store_calls == 0


@pytest.mark.asyncio
async def test_memory_middleware_outline_roundtrip_reads_writes_and_stores_territory_map():
    stub = _StubSessionEnabled()
    mw = MemoryMiddleware(session_factory=lambda _tid: stub)
    agent = _SimpleAgent(
        agent_id=uuid.uuid4(),
        name="outline",
        role="outline",
        layer=2,
        llm_client=_DummyLLM(),
        middlewares=(),
    )
    ctx = {"task_id": "t2", "title": "outline topic", "node_id": "n1"}

    after_before = await mw.before_task(agent, ctx)
    assert "existing context" in after_before["memory_context"]

    out = await mw.after_task(agent, after_before, "outline result")
    assert out == "outline result"
    assert len(stub.stored) == 1
    assert stub.territory_calls == 1
    assert stub.stored[0][1]["role"] == "outline"


@pytest.mark.asyncio
async def test_memory_middleware_writer_roundtrip_uses_query_context_and_stores_metadata():
    stub = _StubSessionEnabled()
    mw = MemoryMiddleware(session_factory=lambda _tid: stub)
    agent = _SimpleAgent(
        agent_id=uuid.uuid4(),
        name="writer",
        role="writer",
        layer=2,
        llm_client=_DummyLLM(),
        middlewares=(),
    )
    ctx = {
        "task_id": "t3",
        "title": "write chapter 1",
        "payload": {
            "chapter_index": 1,
            "chapter_title": "Introduction",
            "assigned_evidence": ["Smith 2024"],
        },
    }

    after_before = await mw.before_task(agent, ctx)
    assert "existing context" in after_before["memory_context"]

    out = await mw.after_task(agent, after_before, "chapter result")
    assert out == "chapter result"
    assert len(stub.stored) == 1
    assert stub.stored[0][1]["role"] == "writer"
    assert stub.stored[0][1]["chapter_index"] == 1


@pytest.mark.asyncio
async def test_memory_middleware_consistency_role_injects_memory_context():
    stub = _StubSessionEnabled()
    mw = MemoryMiddleware(session_factory=lambda _tid: stub)
    agent = _SimpleAgent(
        agent_id=uuid.uuid4(),
        name="consistency",
        role="consistency",
        layer=2,
        llm_client=_DummyLLM(),
        middlewares=(),
    )
    ctx = {"task_id": "t4", "title": "consistency pass"}

    after_before = await mw.before_task(agent, ctx)
    assert "existing context" in after_before["memory_context"]


class _StubSessionQueryFails:
    async def initialize(self):
        return True

    async def query(self, query: str, limit: int = 5):
        raise RuntimeError("query failed")

    async def store(self, content: str, metadata=None):
        return None

    async def store_territory_map(self, content: str):
        return {}


class _StubSessionStoreFails:
    async def initialize(self):
        return True

    async def query(self, query: str, limit: int = 5):
        return [{"content": "existing context"}]

    async def store(self, content: str, metadata=None):
        raise RuntimeError("store failed")

    async def store_territory_map(self, content: str):
        raise RuntimeError("territory failed")


@pytest.mark.asyncio
async def test_memory_middleware_degrades_gracefully_when_query_fails():
    mw = MemoryMiddleware(session_factory=lambda _tid: _StubSessionQueryFails())
    agent = _SimpleAgent(
        agent_id=uuid.uuid4(),
        name="writer",
        role="writer",
        layer=2,
        llm_client=_DummyLLM(),
        middlewares=(),
    )

    result = await mw.before_task(agent, {"task_id": "t5", "title": "chapter"})
    assert result["memory_context"] == ""


@pytest.mark.asyncio
async def test_memory_middleware_degrades_gracefully_when_store_fails():
    mw = MemoryMiddleware(session_factory=lambda _tid: _StubSessionStoreFails())
    agent = _SimpleAgent(
        agent_id=uuid.uuid4(),
        name="outline",
        role="outline",
        layer=2,
        llm_client=_DummyLLM(),
        middlewares=(),
    )
    ctx = {"task_id": "t6", "title": "outline topic"}

    after_before = await mw.before_task(agent, ctx)
    out = await mw.after_task(agent, after_before, "outline result")
    assert out == "outline result"


@pytest.mark.asyncio
async def test_memory_middleware_caps_cached_sessions():
    created: dict[str, _StubSessionEnabled] = {}

    def factory(task_id: str):
        session = _StubSessionEnabled()
        created[task_id] = session
        return session

    mw = MemoryMiddleware(session_factory=factory, max_cached_sessions=2)
    agent = _SimpleAgent(
        agent_id=uuid.uuid4(),
        name="writer",
        role="writer",
        layer=2,
        llm_client=_DummyLLM(),
        middlewares=(),
    )

    await mw.before_task(agent, {"task_id": "t7", "title": "one"})
    await mw.before_task(agent, {"task_id": "t8", "title": "two"})
    await mw.before_task(agent, {"task_id": "t9", "title": "three"})

    assert list(mw._sessions.keys()) == ["t8", "t9"]
