"""Core agent tests for the layered runtime and middleware pipeline.

Strategy:
- use a local mock LLM client instead of external APIs
- keep tests unit-scoped without database dependencies
- validate middleware order, orchestration, and role dispatching
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.base_agent import BaseAgent
from app.agents.agent_registry import AgentRegistry
from app.agents.middleware import (
    AgentMiddleware,
    ContextSummaryMiddleware,
    DEFAULT_MIDDLEWARES,
    LoggingMiddleware,
    MemoryMiddleware,
    TimeoutMiddleware,
    TokenTrackingMiddleware,
)
from app.agents.orchestrator import OrchestratorAgent
from app.agents.manager import ManagerAgent
from app.agents.consistency_agent import ConsistencyAgent
from app.agents.outline_agent import OutlineAgent
from app.agents.researcher_agent import ResearcherAgent
from app.agents.reviewer_agent import ReviewerAgent
from app.agents.worker import WorkerAgent
from app.agents.writer_agent import WriterAgent
from app.utils.token_tracker import TokenTracker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class MockLLMClient:
    """Small in-file mock used by this test module only."""

    def __init__(self) -> None:
        self.call_log: list[dict[str, Any]] = []

    async def chat(
        self, messages, *, model=None, role=None, max_tokens=None, temperature=0.7,
    ) -> str:
        self.call_log.append(
            {"method": "chat", "role": role, "messages": messages, "model": model}
        )
        if role == "outline":
            return "# Outline\n## Chapter 1 Introduction\n## Chapter 2 Core Concepts"
        if role == "writer":
            return "This is a mock chapter section. " * 5
        if role == "reviewer":
            return "Review passed with score 5."
        if role == "consistency":
            return "Consistency check passed."
        if role == "manager":
            return "Manager decision: continue as planned."
        return "mock response"

    async def chat_json(
        self,
        messages,
        *,
        model=None,
        role=None,
        schema=None,
        max_tokens=None,
        max_retries=None,
        fallback_models=None,
    ) -> dict:
        self.call_log.append({"method": "chat_json", "role": role})
        if role == "orchestrator":
            return {
                "nodes": [
                    {"id": "n1", "title": "Generate outline", "role": "outline", "depends_on": []},
                    {"id": "n2", "title": "Write chapter 1", "role": "writer", "depends_on": ["n1"]},
                ]
            }
        return {"result": "mock"}

    async def chat_stream(self, messages, **kwargs):
        for chunk in ["chunk1", "chunk2"]:
            yield chunk

    async def chat_with_tools(self, messages, tools, **kwargs) -> dict:
        return {"type": "text", "content": "mock"}

    async def embed(self, texts, **kwargs) -> list[list[float]]:
        return [[0.1] * 10 for _ in texts]

@pytest.fixture
def mock_llm():
    return MockLLMClient()


@pytest.fixture
def tracker():
    return TokenTracker()


# ---------------------------------------------------------------------------
# Helper worker subclasses for BaseAgent tests
# ---------------------------------------------------------------------------

class SimpleTestAgent(BaseAgent):
    """Minimal agent that returns a predictable result."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.handled_tasks: list[dict] = []

    async def handle_task(self, ctx: dict[str, Any]) -> str:
        self.handled_tasks.append(ctx)
        return f"done:{ctx.get('title', '')}"


class FailingAgent(BaseAgent):
    """Agent used to exercise error handling."""

    async def handle_task(self, ctx: dict[str, Any]) -> str:
        raise RuntimeError("intentional failure")


class SlowAgent(BaseAgent):
    """Agent used to exercise timeout handling."""

    async def handle_task(self, ctx: dict[str, Any]) -> str:
        await asyncio.sleep(10)
        return "should not reach"


class StaticResultAgent(BaseAgent):
    """Agent used to test event emission paths in _handle_message."""

    def __init__(self, *, result_text: str, **kwargs):
        super().__init__(**kwargs)
        self._result_text = result_text

    async def handle_task(self, ctx: dict[str, Any]) -> str:
        return self._result_text


# ===================================================================
# Test: AgentMiddleware
# ===================================================================

class TestLoggingMiddleware:
    """Logging middleware tests."""

    async def test_before_sets_start_time(self, mock_llm):
        agent = SimpleTestAgent(
            agent_id=uuid.uuid4(), name="test", role="writer",
            layer=2, llm_client=mock_llm, middlewares=(),
        )
        mw = LoggingMiddleware()
        ctx = {"title": "test task", "task_id": "t1", "node_id": "n1"}
        result = await mw.before_task(agent, ctx)
        assert "_start_time" in result

    async def test_after_returns_result_unchanged(self, mock_llm):
        agent = SimpleTestAgent(
            agent_id=uuid.uuid4(), name="test", role="writer",
            layer=2, llm_client=mock_llm, middlewares=(),
        )
        mw = LoggingMiddleware()
        ctx = {"_start_time": 1000.0, "task_id": "t1", "node_id": "n1"}
        result = await mw.after_task(agent, ctx, "hello world")
        assert result == "hello world"

    async def test_before_emits_node_update_event(self, mock_llm):
        agent = SimpleTestAgent(
            agent_id=uuid.uuid4(), name="test", role="writer",
            layer=2, llm_client=mock_llm, middlewares=(),
        )
        mw = LoggingMiddleware()
        with patch("app.agents.middleware.communicator.send_task_event", new_callable=AsyncMock) as mock_event:
            await mw.before_task(agent, {"title": "test task", "task_id": "t1", "node_id": "n1"})
        mock_event.assert_awaited_once()
        assert mock_event.await_args.kwargs["msg_type"] == "node_update"
        assert mock_event.await_args.kwargs["payload"]["status"] == "running"

    async def test_after_emits_completed_node_update_event(self, mock_llm):
        agent = SimpleTestAgent(
            agent_id=uuid.uuid4(), name="test", role="writer",
            layer=2, llm_client=mock_llm, middlewares=(),
        )
        mw = LoggingMiddleware()
        with patch("app.agents.middleware.communicator.send_task_event", new_callable=AsyncMock) as mock_event:
            result = await mw.after_task(agent, {"_start_time": 1000.0, "task_id": "t1", "node_id": "n1"}, "hello world")
        assert result == "hello world"
        mock_event.assert_awaited_once()
        assert mock_event.await_args.kwargs["payload"]["status"] == "completed"

    async def test_on_error_emits_failed_node_update_event(self, mock_llm):
        agent = SimpleTestAgent(
            agent_id=uuid.uuid4(), name="test", role="writer",
            layer=2, llm_client=mock_llm, middlewares=(),
        )
        mw = LoggingMiddleware()
        with patch("app.agents.middleware.communicator.send_task_event", new_callable=AsyncMock) as mock_event:
            await mw.on_error(agent, {"_start_time": 1000.0, "task_id": "t1", "node_id": "n1"}, RuntimeError("boom"))
        mock_event.assert_awaited_once()
        assert mock_event.await_args.kwargs["payload"]["status"] == "failed"
        assert mock_event.await_args.kwargs["payload"]["error_code"] == "agent_execution_failed"
        assert mock_event.await_args.kwargs["payload"]["error_message"] == "Task execution failed"
        assert "error" not in mock_event.await_args.kwargs["payload"]


class TestTokenTrackingMiddleware:
    """Token tracking middleware tests."""

    async def test_records_usage_when_present(self, mock_llm, tracker):
        agent = SimpleTestAgent(
            agent_id=uuid.uuid4(), name="test", role="writer",
            layer=2, llm_client=mock_llm, token_tracker=tracker, middlewares=(),
        )
        mw = TokenTrackingMiddleware()
        ctx = {
            "task_id": "task-1",
            "_token_usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "cached_tokens": 10,
            },
        }
        await mw.after_task(agent, ctx, "result")
        usage = tracker.get_role_usage("writer")
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.cached_tokens == 10
        assert usage.call_count == 1

    async def test_no_crash_without_tracker(self, mock_llm):
        agent = SimpleTestAgent(
            agent_id=uuid.uuid4(), name="test", role="writer",
            layer=2, llm_client=mock_llm, token_tracker=None, middlewares=(),
        )
        mw = TokenTrackingMiddleware()
        ctx = {"_token_usage": {"prompt_tokens": 100, "completion_tokens": 50}}
        result = await mw.after_task(agent, ctx, "result")
        assert result == "result"

    async def test_no_crash_without_usage(self, mock_llm, tracker):
        agent = SimpleTestAgent(
            agent_id=uuid.uuid4(), name="test", role="writer",
            layer=2, llm_client=mock_llm, token_tracker=tracker, middlewares=(),
        )
        mw = TokenTrackingMiddleware()
        ctx = {}
        result = await mw.after_task(agent, ctx, "result")
        assert result == "result"
        assert tracker.get_role_usage("writer").call_count == 0


class TestTimeoutMiddleware:
    """Timeout middleware tests."""

    async def test_sets_timeout_in_context(self, mock_llm):
        agent = SimpleTestAgent(
            agent_id=uuid.uuid4(), name="test", role="writer",
            layer=2, llm_client=mock_llm, middlewares=(),
        )
        mw = TimeoutMiddleware(timeout_seconds=30.0)
        ctx = {}
        result = await mw.before_task(agent, ctx)
        assert result["_timeout_seconds"] == 30.0

    async def test_default_timeout(self, mock_llm):
        mw = TimeoutMiddleware()
        agent = SimpleTestAgent(
            agent_id=uuid.uuid4(), name="test", role="writer",
            layer=2, llm_client=mock_llm, middlewares=(),
        )
        ctx = await mw.before_task(agent, {})
        assert ctx["_timeout_seconds"] == 300.0


class TestContextSummaryMiddleware:
    """Context summary middleware tests."""

    async def test_no_compression_for_short_context(self, mock_llm):
        agent = SimpleTestAgent(
            agent_id=uuid.uuid4(), name="test", role="writer",
            layer=2, llm_client=mock_llm, middlewares=(),
        )
        mw = ContextSummaryMiddleware()
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "short message"},
        ]
        ctx = {"messages": messages}
        result = await mw.before_task(agent, ctx)
        assert result["messages"] == messages  # unchanged

    async def test_compression_for_long_context(self, mock_llm):
        agent = SimpleTestAgent(
            agent_id=uuid.uuid4(), name="test", role="writer",
            layer=2, llm_client=mock_llm, middlewares=(),
        )
        mw = ContextSummaryMiddleware()
        # ?
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "x" * 15000},
            {"role": "assistant", "content": "y" * 15000},
            {"role": "user", "content": "recent question"},
            {"role": "assistant", "content": "recent answer"},
        ]
        ctx = {"messages": messages}
        result = await mw.before_task(agent, ctx)
        # ?
        assert len(result["messages"]) < len(messages)


# ===================================================================
# Test: BaseAgent
# ===================================================================

class TestBaseAgent:
    """Base agent tests."""

    async def test_process_task_calls_handle_task(self, mock_llm):
        agent = SimpleTestAgent(
            agent_id=uuid.uuid4(), name="test_agent", role="writer",
            layer=2, llm_client=mock_llm, middlewares=(),
        )
        result = await agent.process_task({"title": "test", "task_id": "t1"})
        assert result == "done:test"
        assert len(agent.handled_tasks) == 1

    async def test_process_task_with_default_middlewares(self, mock_llm):
        agent = SimpleTestAgent(
            agent_id=uuid.uuid4(), name="test_agent", role="writer",
            layer=2, llm_client=mock_llm,
        )
        result = await agent.process_task({
            "title": "with middleware", "task_id": "t1", "node_id": "n1",
        })
        assert result == "done:with middleware"

    async def test_process_task_timeout(self, mock_llm):
        agent = SlowAgent(
            agent_id=uuid.uuid4(), name="slow", role="writer",
            layer=2, llm_client=mock_llm,
            middlewares=(TimeoutMiddleware(timeout_seconds=0.1),),
        )
        with pytest.raises(TimeoutError):
            await agent.process_task({"title": "slow task", "task_id": "t1"})

    async def test_process_task_error_calls_middleware_on_error(self, mock_llm):
        error_log: list[Exception] = []

        class TrackingMiddleware(AgentMiddleware):
            async def on_error(self, agent, ctx, error):
                error_log.append(error)

        agent = FailingAgent(
            agent_id=uuid.uuid4(), name="fail", role="writer",
            layer=2, llm_client=mock_llm,
            middlewares=(TrackingMiddleware(),),
        )
        with pytest.raises(RuntimeError, match="intentional failure"):
            await agent.process_task({"title": "fail task", "task_id": "t1"})
        assert len(error_log) == 1
        assert "intentional" in str(error_log[0])

    async def test_agent_attributes(self, mock_llm):
        aid = uuid.uuid4()
        agent = SimpleTestAgent(
            agent_id=aid, name="my_agent", role="writer",
            layer=2, llm_client=mock_llm,
        )
        assert agent.agent_id == aid
        assert agent.name == "my_agent"
        assert agent.role == "writer"
        assert agent.layer == 2

    async def test_stop_sets_event(self, mock_llm):
        agent = SimpleTestAgent(
            agent_id=uuid.uuid4(), name="test", role="writer",
            layer=2, llm_client=mock_llm,
        )
        assert not agent._stop.is_set()
        agent.stop()
        assert agent._stop.is_set()

    async def test_handle_message_writer_emits_chapter_preview(self, mock_llm):
        agent = StaticResultAgent(
            agent_id=uuid.uuid4(),
            name="writer-events",
            role="writer",
            layer=2,
            llm_client=mock_llm,
            middlewares=(),
            result_text="Paragraph one.\n\nParagraph two.",
        )
        envelope = MagicMock()
        envelope.task_id = "t1"
        envelope.node_id = "n1"
        envelope.payload = {"title": "Write chapter", "chapter_index": 1, "chapter_title": "Intro"}
        with (
            patch.object(agent, "_publish_heartbeat", new_callable=AsyncMock),
            patch("app.agents.base_agent.communicator.send_task_result", new_callable=AsyncMock),
            patch("app.agents.base_agent.communicator.send_task_event", new_callable=AsyncMock) as mock_event,
        ):
            await agent._handle_message(envelope)

        assert any(call.kwargs["msg_type"] == "chapter_preview" for call in mock_event.await_args_list)

    async def test_handle_message_reviewer_emits_review_score(self, mock_llm):
        agent = StaticResultAgent(
            agent_id=uuid.uuid4(),
            name="reviewer-events",
            role="reviewer",
            layer=2,
            llm_client=mock_llm,
            middlewares=(),
            result_text="Review complete. Score: 85.",
        )
        envelope = MagicMock()
        envelope.task_id = "t1"
        envelope.node_id = "n1"
        envelope.payload = {"title": "Review chapter"}
        with (
            patch.object(agent, "_publish_heartbeat", new_callable=AsyncMock),
            patch("app.agents.base_agent.communicator.send_task_result", new_callable=AsyncMock),
            patch("app.agents.base_agent.communicator.send_task_event", new_callable=AsyncMock) as mock_event,
        ):
            await agent._handle_message(envelope)

        review_calls = [call for call in mock_event.await_args_list if call.kwargs["msg_type"] == "review_score"]
        assert len(review_calls) == 1
        assert review_calls[0].kwargs["payload"]["score"] == 85

    async def test_handle_message_consistency_emits_consistency_result(self, mock_llm):
        agent = StaticResultAgent(
            agent_id=uuid.uuid4(),
            name="consistency-events",
            role="consistency",
            layer=2,
            llm_client=mock_llm,
            middlewares=(),
            result_text="No major consistency issues found.",
        )
        envelope = MagicMock()
        envelope.task_id = "t1"
        envelope.node_id = "n1"
        envelope.payload = {"title": "Consistency check"}
        with (
            patch.object(agent, "_publish_heartbeat", new_callable=AsyncMock),
            patch("app.agents.base_agent.communicator.send_task_result", new_callable=AsyncMock),
            patch("app.agents.base_agent.communicator.send_task_event", new_callable=AsyncMock) as mock_event,
        ):
            await agent._handle_message(envelope)

        assert any(call.kwargs["msg_type"] == "consistency_result" for call in mock_event.await_args_list)


# ===================================================================
# Test: AgentRegistry
# ===================================================================

class TestAgentRegistry:
    """Agent registry tests."""

    def _make_agent(self, mock_llm, role="writer", name="test"):
        return SimpleTestAgent(
            agent_id=uuid.uuid4(), name=name, role=role,
            layer=2, llm_client=mock_llm, middlewares=(),
        )

    async def test_register_and_get(self, mock_llm):
        registry = AgentRegistry()
        agent = self._make_agent(mock_llm)
        registry.register(agent)
        assert registry.get(agent.agent_id) is agent
        assert registry.count == 1

    async def test_register_duplicate_ignored(self, mock_llm):
        registry = AgentRegistry()
        agent = self._make_agent(mock_llm)
        registry.register(agent)
        registry.register(agent)  # should not raise
        assert registry.count == 1

    async def test_unregister(self, mock_llm):
        registry = AgentRegistry()
        agent = self._make_agent(mock_llm)
        registry.register(agent)
        registry.unregister(agent.agent_id)
        assert registry.get(agent.agent_id) is None
        assert registry.count == 0

    async def test_unregister_nonexistent(self, mock_llm):
        registry = AgentRegistry()
        registry.unregister(uuid.uuid4())  # should not raise

    async def test_find_by_role(self, mock_llm):
        registry = AgentRegistry()
        w1 = self._make_agent(mock_llm, role="writer", name="w1")
        w2 = self._make_agent(mock_llm, role="writer", name="w2")
        r1 = self._make_agent(mock_llm, role="reviewer", name="r1")
        registry.register(w1)
        registry.register(w2)
        registry.register(r1)

        writers = registry.find_by_role("writer")
        assert len(writers) == 2
        assert all(a.role == "writer" for a in writers)

        reviewers = registry.find_by_role("reviewer")
        assert len(reviewers) == 1

    async def test_find_by_layer(self, mock_llm):
        registry = AgentRegistry()
        a1 = SimpleTestAgent(
            agent_id=uuid.uuid4(), name="orch", role="orchestrator",
            layer=0, llm_client=mock_llm, middlewares=(),
        )
        a2 = self._make_agent(mock_llm, role="writer")  # layer=2
        registry.register(a1)
        registry.register(a2)

        layer0 = registry.find_by_layer(0)
        assert len(layer0) == 1
        assert layer0[0].role == "orchestrator"

    async def test_list_all(self, mock_llm):
        registry = AgentRegistry()
        a1 = self._make_agent(mock_llm, name="a1")
        a2 = self._make_agent(mock_llm, name="a2")
        registry.register(a1)
        registry.register(a2)
        assert len(registry.list_all()) == 2

    async def test_start_agent_raises_for_unknown(self, mock_llm):
        registry = AgentRegistry()
        with pytest.raises(ValueError, match="Agent not found"):
            await registry.start_agent(uuid.uuid4())

    async def test_stop_all(self, mock_llm):
        registry = AgentRegistry()
        a1 = self._make_agent(mock_llm, name="a1")
        registry.register(a1)
        # stop_all should not raise even without start
        await registry.stop_all()


# ===================================================================
# Test: OrchestratorAgent
# ===================================================================

class TestOrchestratorAgent:
    """Orchestrator agent tests."""

    async def test_handle_task_calls_decompose(self, mock_llm):
        agent = OrchestratorAgent(
            agent_id=uuid.uuid4(), name="orch",
            llm_client=mock_llm, middlewares=(),
        )
        assert agent.role == "orchestrator"
        assert agent.layer == 0

        ctx = {
            "task_id": str(uuid.uuid4()),
            "title": "Write a report on quantum computing",
            "payload": {
                "title": "Write a report on quantum computing",
                "mode": "report",
                "depth": "standard",
                "target_words": 10000,
            },
        }

        result = await agent.handle_task(ctx)

        assert "n1" in result
        assert "n2" in result
        assert "outline" in result
        assert any(c["method"] == "chat_json" for c in mock_llm.call_log)


# ===================================================================
# Test: ManagerAgent
# ===================================================================

class TestManagerAgent:
    """ManagerAgent Layer 1 coordination tests."""

    async def test_coordinator_role(self, mock_llm):
        agent = ManagerAgent(
            agent_id=uuid.uuid4(), name="mgr_coord",
            manager_role="coordinator",
            llm_client=mock_llm, middlewares=(),
        )
        assert agent.role == "manager"
        assert agent.layer == 1
        assert agent.manager_role == "coordinator"

        ctx = {
            "task_id": "t1",
            "title": "coordinate subtasks",
            "payload": {
                "instruction": "Check the progress of all writer agents.",
                "context": "Three writers are working in parallel.",
            },
        }

        result = await agent.handle_task(ctx)
        assert isinstance(result, str)
        assert len(result) > 0
        assert len(mock_llm.call_log) == 1
        assert mock_llm.call_log[0]["role"] == "manager"

    async def test_strategy_role(self, mock_llm):
        agent = ManagerAgent(
            agent_id=uuid.uuid4(), name="mgr_strat",
            manager_role="strategy",
            llm_client=mock_llm, middlewares=(),
        )
        assert agent.manager_role == "strategy"

    async def test_quality_role(self, mock_llm):
        agent = ManagerAgent(
            agent_id=uuid.uuid4(), name="mgr_qual",
            manager_role="quality",
            llm_client=mock_llm, middlewares=(),
        )
        assert agent.manager_role == "quality"

    async def test_invalid_manager_role(self, mock_llm):
        with pytest.raises(ValueError, match="Invalid manager_role"):
            ManagerAgent(
                agent_id=uuid.uuid4(), name="bad",
                manager_role="invalid",
                llm_client=mock_llm,
            )


# ===================================================================
# Test: WorkerAgent
# ===================================================================

class TestWorkerAgent:
    """WorkerAgent Layer 2 execution tests."""

    async def test_handle_task_writer_role(self, mock_llm):
        agent = WorkerAgent(
            agent_id=uuid.uuid4(), name="writer_1",
            role="writer", llm_client=mock_llm, middlewares=(),
        )
        assert agent.layer == 2

        ctx = {
            "task_id": "t1",
            "node_id": "n1",
            "title": "Write chapter 1",
            "agent_role": "writer",
            "payload": {"chapter_index": "1"},
        }
        result = await agent.handle_task(ctx)
        assert len(result) > 0
        assert mock_llm.call_log[-1]["role"] == "writer"

    async def test_handle_task_reviewer_role(self, mock_llm):
        agent = WorkerAgent(
            agent_id=uuid.uuid4(), name="reviewer_1",
            role="reviewer", llm_client=mock_llm, middlewares=(),
        )

        ctx = {
            "task_id": "t1",
            "node_id": "n2",
            "title": "Review chapter 1",
            "agent_role": "reviewer",
            "payload": {},
        }
        result = await agent.handle_task(ctx)
        assert "Review" in result

    async def test_handle_task_outline_role(self, mock_llm):
        agent = WorkerAgent(
            agent_id=uuid.uuid4(), name="outline_1",
            role="outline", llm_client=mock_llm, middlewares=(),
        )

        ctx = {
            "task_id": "t1",
            "node_id": "n3",
            "title": "Generate outline",
            "agent_role": "outline",
            "payload": {},
        }
        result = await agent.handle_task(ctx)
        assert "Outline" in result

    async def test_build_user_prompt_fallback(self, mock_llm):
        """Falls back to the generic prompt format when a template is missing."""
        agent = WorkerAgent(
            agent_id=uuid.uuid4(), name="generic",
            role="writer", llm_client=mock_llm, middlewares=(),
        )
        prompt = agent._build_user_prompt(
            "test title", "unknown_role", {"key": "value"},
        )
        assert "test title" in prompt
        assert "key" in prompt

    async def test_custom_layer(self, mock_llm):
        agent = WorkerAgent(
            agent_id=uuid.uuid4(), name="custom",
            role="writer", layer=2, llm_client=mock_llm, middlewares=(),
        )
        assert agent.layer == 2

    async def test_writer_uses_memory_context_without_prompt_fallback(self, mock_llm):
        agent = WorkerAgent(
            agent_id=uuid.uuid4(), name="writer_ctx",
            role="writer", llm_client=mock_llm, middlewares=(),
        )
        await agent.handle_task(
            {
                "task_id": "t1",
                "node_id": "n1",
                "title": "Write chapter 1",
                "agent_role": "writer",
                "memory_context": "avoid repeating introduction",
                "payload": {"chapter_index": 1, "chapter_title": "Introduction"},
            }
        )
        writer_calls = [
            call for call in mock_llm.call_log
            if call.get("role") == "writer"
        ]
        prompt_calls = [call for call in writer_calls if isinstance(call.get("messages"), list)]
        assert prompt_calls
        user_prompt = prompt_calls[0]["messages"][-1]["content"]
        assert "Memory Context" in user_prompt
        assert "avoid repeating introduction" in user_prompt

    async def test_consistency_payload_is_normalized_for_prompt_contract(self, mock_llm):
        agent = WorkerAgent(
            agent_id=uuid.uuid4(), name="consistency_worker",
            role="consistency", llm_client=mock_llm, middlewares=(),
        )
        await agent.handle_task(
            {
                "task_id": "t1",
                "node_id": "n2",
                "title": "Consistency check",
                "agent_role": "consistency",
                "memory_context": "上一轮已统一术语：MVP=最小可行产品",
                "payload": {"full_draft": "chapter draft text"},
            }
        )
        consistency_calls = [
            call for call in mock_llm.call_log
            if call.get("role") == "consistency"
        ]
        user_prompt = consistency_calls[0]["messages"][-1]["content"]
        assert "Full Text" in user_prompt
        assert "memory_context" in user_prompt
        assert "上一轮已统一术语" in user_prompt

    async def test_quick_low_word_tasks_use_fast_model_override(self, mock_llm):
        agent = WorkerAgent(
            agent_id=uuid.uuid4(), name="writer_fast",
            role="writer", llm_client=mock_llm, middlewares=(),
        )
        await agent.handle_task(
            {
                "task_id": "t1",
                "node_id": "n1",
                "title": "Write quick chapter",
                "agent_role": "writer",
                "payload": {
                    "depth": "quick",
                    "target_words": 1200,
                    "chapter_index": 1,
                    "chapter_title": "Quick Intro",
                },
            }
        )
        writer_calls = [c for c in mock_llm.call_log if c.get("role") == "writer"]
        assert writer_calls
        assert any(call.get("model") == "deepseek-v3.2" for call in writer_calls)

    async def test_writer_repairs_review_style_json_output(self):
        class RepairMockLLM:
            def __init__(self):
                self.calls: list[dict[str, Any]] = []
                self._writer_calls = 0

            async def chat(self, messages, *, role=None, **kwargs):
                self.calls.append({"role": role, "messages": messages})
                if role == "writer":
                    self._writer_calls += 1
                    if self._writer_calls == 1:
                        return '{"score": 80, "must_fix": [], "feedback": "ok", "pass": true}'
                    return "# Chapter 1\n\nThis chapter is repaired markdown prose."
                return "ok"

        llm = RepairMockLLM()
        agent = WorkerAgent(
            agent_id=uuid.uuid4(), name="writer_repair",
            role="writer", llm_client=llm, middlewares=(),
        )
        result = await agent.handle_task(
            {
                "task_id": "t1",
                "node_id": "n1",
                "title": "Write chapter",
                "agent_role": "writer",
                "payload": {"chapter_index": 1, "chapter_title": "Chapter 1"},
            }
        )
        parsed = json.loads(result)
        assert parsed["chapter_title"] == "Chapter 1"
        assert parsed["content_markdown"].startswith("# Chapter 1")
        assert len(llm.calls) >= 2

    async def test_reviewer_repairs_invalid_non_json_output(self):
        class ReviewerRepairMockLLM:
            def __init__(self):
                self.calls: list[dict[str, Any]] = []
                self._review_calls = 0

            async def chat(self, messages, *, role=None, **kwargs):
                self.calls.append({"role": role, "messages": messages})
                if role == "reviewer":
                    self._review_calls += 1
                    if self._review_calls == 1:
                        return "looks good"
                    return '{"score": 75, "must_fix": [], "feedback": "ok", "pass": true}'
                return "ok"

        llm = ReviewerRepairMockLLM()
        agent = WorkerAgent(
            agent_id=uuid.uuid4(), name="reviewer_repair",
            role="reviewer", llm_client=llm, middlewares=(),
        )
        result = await agent.handle_task(
            {
                "task_id": "t1",
                "node_id": "n2",
                "title": "Review chapter",
                "agent_role": "reviewer",
                "payload": {"chapter_index": 1, "chapter_title": "Chapter 1"},
            }
        )
        assert result.startswith("{")
        assert len(llm.calls) >= 2


# ===================================================================
# Test: Middleware Pipeline Integration
# ===================================================================

class TestMiddlewarePipeline:
    """Middleware pipeline integration tests."""

    async def test_full_pipeline_success(self, mock_llm, tracker):
        """Runs the full default middleware pipeline successfully."""
        agent = SimpleTestAgent(
            agent_id=uuid.uuid4(), name="test", role="writer",
            layer=2, llm_client=mock_llm, token_tracker=tracker,
        )
        ctx = {
            "title": "test task",
            "task_id": "t1",
            "node_id": "n1",
        }
        result = await agent.process_task(ctx)
        assert "done:test task" in result

    async def test_middleware_order(self, mock_llm):
        """Executes middlewares in before-order and reverse after-order."""
        order: list[str] = []

        class OrderTracker(AgentMiddleware):
            def __init__(self, name: str):
                self._name = name

            async def before_task(self, agent, ctx):
                order.append(f"before:{self._name}")
                return ctx

            async def after_task(self, agent, ctx, result):
                order.append(f"after:{self._name}")
                return result

        agent = SimpleTestAgent(
            agent_id=uuid.uuid4(), name="test", role="writer",
            layer=2, llm_client=mock_llm,
            middlewares=(OrderTracker("A"), OrderTracker("B")),
        )
        await agent.process_task({"title": "t", "task_id": "t1"})

        # before: A -> B, after: B -> A
        assert order == ["before:A", "before:B", "after:B", "after:A"]

    async def test_error_propagates_through_middlewares(self, mock_llm):
        """Propagates errors through all middleware on_error hooks."""
        errors: list[str] = []

        class ErrorTracker(AgentMiddleware):
            def __init__(self, name: str):
                self._name = name

            async def on_error(self, agent, ctx, error):
                errors.append(self._name)

        agent = FailingAgent(
            agent_id=uuid.uuid4(), name="fail", role="writer",
            layer=2, llm_client=mock_llm,
            middlewares=(ErrorTracker("A"), ErrorTracker("B")),
        )

        with pytest.raises(RuntimeError):
            await agent.process_task({"title": "fail", "task_id": "t1"})

        # both middlewares should receive on_error
        assert "A" in errors
        assert "B" in errors

    async def test_default_middlewares_count(self):
        """Default middleware stack should include role-aware memory integration."""
        assert len(DEFAULT_MIDDLEWARES) == 5
        assert isinstance(DEFAULT_MIDDLEWARES[0], LoggingMiddleware)
        assert isinstance(DEFAULT_MIDDLEWARES[1], TokenTrackingMiddleware)
        assert isinstance(DEFAULT_MIDDLEWARES[2], TimeoutMiddleware)
        assert isinstance(DEFAULT_MIDDLEWARES[3], ContextSummaryMiddleware)
        assert isinstance(DEFAULT_MIDDLEWARES[4], MemoryMiddleware)


class TestSpecializedAgentPayloadPassthrough:
    """Dedicated role agents should preserve depth/target_words for fast-path routing."""

    async def test_outline_agent_preserves_depth(self, mock_llm):
        agent = OutlineAgent(agent_id=uuid.uuid4(), name="outline", llm_client=mock_llm, middlewares=())
        with patch.object(WorkerAgent, "handle_task", new_callable=AsyncMock, return_value="ok") as mocked:
            await agent.handle_task(
                {
                    "agent_role": "outline",
                    "title": "Generate outline",
                    "payload": {"depth": "quick", "target_words": 1200},
                }
            )
        forwarded = mocked.await_args.args[0]["payload"]
        assert forwarded["depth"] == "quick"
        assert forwarded["target_words"] == 1200

    async def test_writer_agent_preserves_depth(self, mock_llm):
        agent = WriterAgent(agent_id=uuid.uuid4(), name="writer", llm_client=mock_llm, middlewares=())
        with patch.object(WorkerAgent, "handle_task", new_callable=AsyncMock, return_value="ok") as mocked:
            await agent.handle_task(
                {
                    "agent_role": "writer",
                    "title": "Write chapter 1",
                    "payload": {"depth": "quick", "target_words": 1200, "chapter_title": "Intro"},
                }
            )
        forwarded = mocked.await_args.args[0]["payload"]
        assert forwarded["depth"] == "quick"
        assert forwarded["target_words"] == 1200

    async def test_researcher_agent_preserves_depth(self, mock_llm):
        agent = ResearcherAgent(
            agent_id=uuid.uuid4(), name="researcher", llm_client=mock_llm, middlewares=()
        )
        with patch.object(WorkerAgent, "handle_task", new_callable=AsyncMock, return_value="ok") as mocked:
            await agent.handle_task(
                {
                    "agent_role": "researcher",
                    "title": "Research task",
                    "payload": {"depth": "quick", "target_words": 900},
                }
            )
        forwarded = mocked.await_args.args[0]["payload"]
        assert forwarded["depth"] == "quick"
        assert forwarded["target_words"] == 900

    async def test_reviewer_agent_preserves_depth_and_target_words(self, mock_llm):
        agent = ReviewerAgent(
            agent_id=uuid.uuid4(), name="reviewer", llm_client=mock_llm, middlewares=()
        )
        with patch.object(WorkerAgent, "handle_task", new_callable=AsyncMock, return_value="ok") as mocked:
            await agent.handle_task(
                {
                    "agent_role": "reviewer",
                    "title": "Review chapter",
                    "payload": {"depth": "quick", "target_words": 1200, "chapter_title": "Intro"},
                }
            )
        forwarded = mocked.await_args.args[0]["payload"]
        assert forwarded["depth"] == "quick"
        assert forwarded["target_words"] == 1200

    async def test_consistency_agent_preserves_depth_and_target_words(self, mock_llm):
        agent = ConsistencyAgent(
            agent_id=uuid.uuid4(), name="consistency", llm_client=mock_llm, middlewares=()
        )
        with patch.object(WorkerAgent, "handle_task", new_callable=AsyncMock, return_value="ok") as mocked:
            await agent.handle_task(
                {
                    "agent_role": "consistency",
                    "title": "Consistency check",
                    "payload": {"depth": "quick", "target_words": 1200, "full_text": "draft"},
                }
            )
        forwarded = mocked.await_args.args[0]["payload"]
        assert forwarded["depth"] == "quick"
        assert forwarded["target_words"] == 1200
