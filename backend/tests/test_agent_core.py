"""Tests for Step 3.3 — Agent基类 + 层级Agent + 中间件 + 注册表

测试策略：
  - 使用 MockLLMClient（不调用外部API）
  - 使用 fakeredis（不依赖真实Redis）
  - 直接单元测试各组件，不依赖 DB
"""

from __future__ import annotations

import asyncio
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
from app.agents.worker import WorkerAgent
from app.utils.token_tracker import TokenTracker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class MockLLMClient:
    """内联 MockLLMClient — 不依赖 conftest 中的完整版本"""

    def __init__(self) -> None:
        self.call_log: list[dict[str, Any]] = []

    async def chat(
        self, messages, *, model=None, role=None, max_tokens=None, temperature=0.7,
    ) -> str:
        self.call_log.append({"method": "chat", "role": role, "messages": messages})
        if role == "outline":
            return "# 大纲\n## 第1章 引言\n## 第2章 核心"
        if role == "writer":
            return "这是一段模拟章节内容。" * 5
        if role == "reviewer":
            return "审查通过，评分85分。"
        if role == "consistency":
            return "一致性检查通过。"
        if role == "manager":
            return "管理决策：按计划执行。"
        return "mock response"

    async def chat_json(
        self, messages, *, model=None, role=None, schema=None, max_tokens=None,
    ) -> dict:
        self.call_log.append({"method": "chat_json", "role": role})
        if role == "orchestrator":
            return {
                "nodes": [
                    {"id": "n1", "title": "大纲生成", "role": "outline", "depends_on": []},
                    {"id": "n2", "title": "第1章撰写", "role": "writer", "depends_on": ["n1"]},
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
# Helper — 简单的 Worker 子类用于测试 BaseAgent
# ---------------------------------------------------------------------------

class SimpleTestAgent(BaseAgent):
    """最简测试 Agent — handle_task 直接返回固定内容"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.handled_tasks: list[dict] = []

    async def handle_task(self, ctx: dict[str, Any]) -> str:
        self.handled_tasks.append(ctx)
        return f"done:{ctx.get('title', '')}"


class FailingAgent(BaseAgent):
    """总是失败的 Agent"""

    async def handle_task(self, ctx: dict[str, Any]) -> str:
        raise RuntimeError("intentional failure")


class SlowAgent(BaseAgent):
    """超时 Agent"""

    async def handle_task(self, ctx: dict[str, Any]) -> str:
        await asyncio.sleep(10)
        return "should not reach"


# ===================================================================
# Test: AgentMiddleware
# ===================================================================

class TestLoggingMiddleware:
    """LoggingMiddleware 日志中间件"""

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


class TestTokenTrackingMiddleware:
    """TokenTrackingMiddleware Token 追踪"""

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
    """TimeoutMiddleware 超时控制"""

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
        assert ctx["_timeout_seconds"] == 120.0


class TestContextSummaryMiddleware:
    """ContextSummaryMiddleware 上下文压缩"""

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
        # 创建超长上下文
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "x" * 15000},
            {"role": "assistant", "content": "y" * 15000},
            {"role": "user", "content": "recent question"},
            {"role": "assistant", "content": "recent answer"},
        ]
        ctx = {"messages": messages}
        result = await mw.before_task(agent, ctx)
        # 应该被压缩，消息数量减少
        assert len(result["messages"]) < len(messages)


# ===================================================================
# Test: BaseAgent
# ===================================================================

class TestBaseAgent:
    """BaseAgent 基类测试"""

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


# ===================================================================
# Test: AgentRegistry
# ===================================================================

class TestAgentRegistry:
    """AgentRegistry Agent注册表"""

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
    """OrchestratorAgent Layer 0 编排Agent"""

    async def test_handle_task_calls_decompose(self, mock_llm):
        agent = OrchestratorAgent(
            agent_id=uuid.uuid4(), name="orch",
            llm_client=mock_llm, middlewares=(),
        )
        assert agent.role == "orchestrator"
        assert agent.layer == 0

        ctx = {
            "task_id": str(uuid.uuid4()),
            "title": "写一篇量子计算技术报告",
            "payload": {
                "title": "写一篇量子计算技术报告",
                "mode": "report",
                "depth": "standard",
                "target_words": 10000,
            },
        }

        result = await agent.handle_task(ctx)

        # decompose_task 内部调用 mock_llm.chat_json(role="orchestrator")
        # 返回 MOCK_DAG_JSON, 序列化为 JSON string
        assert "n1" in result
        assert "n2" in result
        assert "outline" in result

        # 确认 LLM 被调用
        assert any(c["method"] == "chat_json" for c in mock_llm.call_log)


# ===================================================================
# Test: ManagerAgent
# ===================================================================

class TestManagerAgent:
    """ManagerAgent Layer 1 管理Agent"""

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
                "instruction": "检查所有写作Agent的进度",
                "context": "3个Writer正在并行工作",
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
    """WorkerAgent Layer 2 通用执行Agent"""

    async def test_handle_task_writer_role(self, mock_llm):
        agent = WorkerAgent(
            agent_id=uuid.uuid4(), name="writer_1",
            role="writer", llm_client=mock_llm, middlewares=(),
        )
        assert agent.layer == 2

        ctx = {
            "task_id": "t1",
            "node_id": "n1",
            "title": "撰写第1章",
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
            "title": "审查第1章",
            "agent_role": "reviewer",
            "payload": {},
        }
        result = await agent.handle_task(ctx)
        assert "审查" in result

    async def test_handle_task_outline_role(self, mock_llm):
        agent = WorkerAgent(
            agent_id=uuid.uuid4(), name="outline_1",
            role="outline", llm_client=mock_llm, middlewares=(),
        )

        ctx = {
            "task_id": "t1",
            "node_id": "n3",
            "title": "生成大纲",
            "agent_role": "outline",
            "payload": {},
        }
        result = await agent.handle_task(ctx)
        assert "大纲" in result

    async def test_build_user_prompt_fallback(self, mock_llm):
        """当 Prompt 模板不存在时使用通用格式"""
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


# ===================================================================
# Test: Middleware Pipeline Integration
# ===================================================================

class TestMiddlewarePipeline:
    """中间件管道集成测试"""

    async def test_full_pipeline_success(self, mock_llm, tracker):
        """完整中间件管道 — 成功路径"""
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
        """验证中间件执行顺序"""
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

        # before: A → B, after: B → A（逆序）
        assert order == ["before:A", "before:B", "after:B", "after:A"]

    async def test_error_propagates_through_middlewares(self, mock_llm):
        """异常应该触发所有中间件的 on_error"""
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

        # 两个中间件都应收到 on_error
        assert "A" in errors
        assert "B" in errors

    async def test_default_middlewares_count(self):
        """默认中间件应该有4个"""
        assert len(DEFAULT_MIDDLEWARES) == 5
        assert isinstance(DEFAULT_MIDDLEWARES[0], LoggingMiddleware)
        assert isinstance(DEFAULT_MIDDLEWARES[1], TokenTrackingMiddleware)
        assert isinstance(DEFAULT_MIDDLEWARES[2], TimeoutMiddleware)
        assert isinstance(DEFAULT_MIDDLEWARES[3], ContextSummaryMiddleware)
        assert isinstance(DEFAULT_MIDDLEWARES[4], MemoryMiddleware)
