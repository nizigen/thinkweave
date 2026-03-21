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
    async def initialize(self):
        return False

    async def query(self, query: str, limit: int = 5):
        return []

    async def store(self, content: str, metadata=None):
        return None

    async def store_territory_map(self, content: str):
        return {}


class _StubSessionEnabled:
    def __init__(self):
        self.stored: list[tuple[str, dict[str, Any] | None]] = []
        self.territory_calls = 0

    async def initialize(self):
        return True

    async def query(self, query: str, limit: int = 5):
        return [{"content": "existing context"}]

    async def store(self, content: str, metadata=None):
        self.stored.append((content, metadata))
        return None

    async def store_territory_map(self, content: str):
        self.territory_calls += 1
        return {}


@pytest.mark.asyncio
async def test_memory_middleware_disabled_mode():
    mw = MemoryMiddleware(session_factory=lambda _tid: _StubSessionDisabled())
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


@pytest.mark.asyncio
async def test_memory_middleware_enabled_mode_read_write():
    stub = _StubSessionEnabled()
    mw = MemoryMiddleware(session_factory=lambda _tid: stub)
    agent = _SimpleAgent(
        agent_id=uuid.uuid4(),
        name="outline",
        role="outline",
        layer=1,
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
