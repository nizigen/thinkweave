"""Tests for review findings fixes and regressions."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fix 2: datetime.utcnow deprecation
# ---------------------------------------------------------------------------

class TestDatetimeUtcnow:
    """Task/Outline/ChapterReview created_at defaults must use lambda (not datetime.utcnow directly)."""

    def test_task_created_at_is_lambda(self):
        from datetime import datetime
        from app.models.task import Task
        col = Task.__table__.columns["created_at"]
        # datetime.utcnow is a builtin_function_or_method; our lambda is a function
        assert callable(col.default.arg)
        assert col.default.arg is not datetime.utcnow

    def test_outline_created_at_is_lambda(self):
        from datetime import datetime
        from app.models.task import Outline
        col = Outline.__table__.columns["created_at"]
        assert callable(col.default.arg)
        assert col.default.arg is not datetime.utcnow

    def test_chapter_review_created_at_is_lambda(self):
        from datetime import datetime
        from app.models.task import ChapterReview
        col = ChapterReview.__table__.columns["created_at"]
        assert callable(col.default.arg)
        assert col.default.arg is not datetime.utcnow


# ---------------------------------------------------------------------------
# Fix 3: swallowed exception → log warning
# ---------------------------------------------------------------------------

class TestContextSummaryExceptionLogging:

    async def test_no_raise_on_config_failure(self):
        from app.agents.middleware import ContextSummaryMiddleware
        from app.agents.base_agent import BaseAgent

        mw = ContextSummaryMiddleware()

        class Dummy(BaseAgent):
            async def handle_task(self, ctx):
                return ""

        class FakeLLM:
            def get_model_config(self, role):
                raise RuntimeError("boom")

        agent = Dummy(
            agent_id=uuid.uuid4(), name="d", role="writer",
            layer=2, llm_client=FakeLLM(), middlewares=(),
        )
        ctx = {"messages": [{"role": "user", "content": "short"}]}
        result = await mw.before_task(agent, ctx)
        assert result is ctx  # short context, unchanged


# ---------------------------------------------------------------------------
# Fix 4: _consume_errors not initialized
# ---------------------------------------------------------------------------

class TestConsumeErrorsInit:

    def test_has_consume_errors_attr(self):
        from app.agents.base_agent import BaseAgent

        class Dummy(BaseAgent):
            async def handle_task(self, ctx):
                return ""

        agent = Dummy(
            agent_id=uuid.uuid4(), name="d", role="writer",
            layer=2, llm_client=MagicMock(), middlewares=(),
        )
        assert hasattr(agent, "_consume_errors")
        assert agent._consume_errors == 0

    @pytest.mark.asyncio
    async def test_publish_heartbeat_tracks_current_runtime_state(self):
        from app.agents.base_agent import BaseAgent

        class Dummy(BaseAgent):
            async def handle_task(self, ctx):
                return ""

        agent = Dummy(
            agent_id=uuid.uuid4(),
            name="d",
            role="writer",
            layer=2,
            llm_client=MagicMock(),
            middlewares=(),
        )

        with patch("app.agents.base_agent.send_heartbeat", new_callable=AsyncMock) as mock_send:
            await agent._publish_heartbeat(
                status="busy",
                current_task="task-1",
                current_node="node-1",
            )

        assert agent._heartbeat_status == "busy"
        assert agent._heartbeat_task == "task-1"
        assert agent._heartbeat_node == "node-1"
        mock_send.assert_awaited_once()


# ---------------------------------------------------------------------------
# Fix 5: LoggingMiddleware ctx mutation
# ---------------------------------------------------------------------------

class TestLoggingMiddlewareImmutability:

    async def test_returns_new_dict(self):
        from app.agents.middleware import LoggingMiddleware
        from app.agents.base_agent import BaseAgent

        mw = LoggingMiddleware()

        class Dummy(BaseAgent):
            async def handle_task(self, ctx):
                return ""

        agent = Dummy(
            agent_id=uuid.uuid4(), name="d", role="writer",
            layer=2, llm_client=MagicMock(), middlewares=(),
        )
        original = {"title": "t", "task_id": "t1", "node_id": "n1"}
        original_copy = dict(original)
        result = await mw.before_task(agent, original)
        assert original == original_copy
        assert "_start_time" in result


class TestTaskAuthorizationBoundary:

    def test_task_visibility_scoped_to_owner(self):
        from app.models.task import Task
        from app.services.task_service import _task_visible_to_user

        task = Task(title="t", mode="report", owner_id="user-a")

        assert _task_visible_to_user(task, user_id="user-a", is_admin=False) is True
        assert _task_visible_to_user(task, user_id="user-b", is_admin=False) is False
        assert _task_visible_to_user(task, user_id="admin", is_admin=True) is True


# ---------------------------------------------------------------------------
# Fix 6: deque optimization
# ---------------------------------------------------------------------------

class TestDequeTopologicalSort:

    def test_uses_deque(self):
        import inspect
        from app.services import task_decomposer
        src = inspect.getsource(task_decomposer.validate_dag_acyclic)
        assert "deque" in src
        assert "queue.pop(0)" not in src


# ---------------------------------------------------------------------------
# Fix 7: LLMClient singleton
# ---------------------------------------------------------------------------

class TestLLMClientSingleton:

    def test_returns_same_instance(self):
        from app.routers.tasks import get_llm_client
        a = get_llm_client()
        b = get_llm_client()
        assert a is b


class TestSettingsNormalization:

    def test_release_debug_string_maps_to_false(self):
        from app.config import Settings

        cfg = Settings(debug="release")
        assert cfg.debug is False

    def test_backend_env_file_is_resolved_relative_to_module(self):
        from pathlib import Path
        from app.config import _BACKEND_ENV_FILE

        expected = Path(__file__).resolve().parents[1] / ".env"
        assert _BACKEND_ENV_FILE == expected


# ---------------------------------------------------------------------------
# Fix 8: MCPServerConfig mutable fields
# ---------------------------------------------------------------------------

class TestMCPServerConfigImmutable:

    def test_args_is_tuple(self):
        from app.mcp.config import MCPServerConfig
        cfg = MCPServerConfig(name="test", command="npx")
        assert isinstance(cfg.args, tuple)

    def test_env_is_tuple(self):
        from app.mcp.config import MCPServerConfig
        cfg = MCPServerConfig(name="test", command="npx")
        assert isinstance(cfg.env, tuple)

    def test_args_not_appendable(self):
        from app.mcp.config import MCPServerConfig
        cfg = MCPServerConfig(name="test", command="npx", args=("--flag",))
        with pytest.raises((TypeError, AttributeError)):
            cfg.args.append("bad")  # type: ignore[union-attr]
