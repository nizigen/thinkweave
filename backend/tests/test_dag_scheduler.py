"""Tests for DAG Scheduler — dag_scheduler.py

测试策略：
  - 使用 fakeredis 替代真实 Redis
  - 使用 SQLite async 替代 PostgreSQL（单元测试不需要真实 DB）
  - Mock communicator 发送，只验证调度逻辑
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.services.dag_scheduler import (
    AGENT_BUSY,
    AGENT_IDLE,
    MAX_RETRIES,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_READY,
    STATUS_RUNNING,
    DAGScheduler,
    get_scheduler,
    start_scheduler,
    stop_scheduler,
    _active_schedulers,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_uuid() -> uuid.UUID:
    return uuid.uuid4()


class FakeNode:
    """模拟 TaskNode ORM 对象。"""

    def __init__(
        self,
        node_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        title: str = "test node",
        agent_role: str = "writer",
        status: str = STATUS_PENDING,
        depends_on: list[uuid.UUID] | None = None,
        retry_count: int = 0,
        assigned_agent: uuid.UUID | None = None,
    ):
        self.id = node_id or make_uuid()
        self.task_id = task_id or make_uuid()
        self.title = title
        self.agent_role = agent_role
        self.status = status
        self.depends_on = depends_on
        self.retry_count = retry_count
        self.assigned_agent = assigned_agent
        self.result = None
        self.started_at = None
        self.finished_at = None


class FakeAgent:
    """模拟 Agent ORM 对象。"""

    def __init__(
        self,
        agent_id: uuid.UUID | None = None,
        name: str = "test-agent",
        role: str = "writer",
        status: str = AGENT_IDLE,
    ):
        self.id = agent_id or make_uuid()
        self.name = name
        self.role = role
        self.status = status
        self.created_at = datetime.now(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def task_id() -> uuid.UUID:
    return make_uuid()


@pytest.fixture
def scheduler(task_id: uuid.UUID) -> DAGScheduler:
    return DAGScheduler(task_id)


# ---------------------------------------------------------------------------
# Test: 基础属性
# ---------------------------------------------------------------------------


class TestDAGSchedulerInit:
    def test_init_sets_task_id(self, task_id: uuid.UUID):
        s = DAGScheduler(task_id)
        assert s.task_id == task_id

    def test_init_empty_running_nodes(self, scheduler: DAGScheduler):
        assert scheduler._running_nodes == {}

    def test_stop_sets_event(self, scheduler: DAGScheduler):
        assert not scheduler._stop.is_set()
        scheduler.stop()
        assert scheduler._stop.is_set()


# ---------------------------------------------------------------------------
# Test: 并发控制 _can_dispatch
# ---------------------------------------------------------------------------


class TestCanDispatch:
    def test_allows_when_under_limit(self, scheduler: DAGScheduler):
        assert scheduler._can_dispatch("writer") is True

    def test_blocks_when_llm_limit_reached(self, scheduler: DAGScheduler):
        # 填满 LLM 并发槽
        for _ in range(5):
            nid = make_uuid()
            scheduler._running_nodes[nid] = make_uuid()
        assert scheduler._can_dispatch("writer") is False

    def test_blocks_writer_when_writer_limit_reached(self, scheduler: DAGScheduler):
        # 填满 writer 并发槽
        for _ in range(3):
            nid = make_uuid()
            scheduler._running_nodes[nid] = make_uuid()
            scheduler._node_roles[nid] = "writer"
        # 总 LLM 并发未满，但 writer 已满
        assert scheduler._can_dispatch("writer") is False
        # 其他角色仍可调度
        assert scheduler._can_dispatch("reviewer") is True

    def test_allows_non_writer_even_when_writers_full(self, scheduler: DAGScheduler):
        for _ in range(3):
            nid = make_uuid()
            scheduler._running_nodes[nid] = make_uuid()
            scheduler._node_roles[nid] = "writer"
        assert scheduler._can_dispatch("outline") is True


# ---------------------------------------------------------------------------
# Test: on_node_completed
# ---------------------------------------------------------------------------


class TestOnNodeCompleted:
    @pytest.mark.asyncio
    async def test_node_completed_removes_from_running(self, scheduler: DAGScheduler):
        node_id = make_uuid()
        agent_id = make_uuid()
        scheduler._running_nodes[node_id] = agent_id

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock),
            patch("app.services.dag_scheduler.remove_timeout_watch", new_callable=AsyncMock),
            patch.object(scheduler, "_activate_dependents", new_callable=AsyncMock),
        ):
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler.on_node_completed(node_id, "result text", agent_id)

        assert node_id not in scheduler._running_nodes

    @pytest.mark.asyncio
    async def test_node_completed_triggers_schedule_event(self, scheduler: DAGScheduler):
        node_id = make_uuid()
        agent_id = make_uuid()
        scheduler._running_nodes[node_id] = agent_id

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock),
            patch("app.services.dag_scheduler.remove_timeout_watch", new_callable=AsyncMock),
            patch.object(scheduler, "_activate_dependents", new_callable=AsyncMock),
        ):
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler.on_node_completed(node_id, "result text", agent_id)

        assert scheduler._schedule_event.is_set()


# ---------------------------------------------------------------------------
# Test: on_node_failed
# ---------------------------------------------------------------------------


class TestOnNodeFailed:
    @pytest.mark.asyncio
    async def test_retries_under_max(self, scheduler: DAGScheduler):
        """失败次数 < MAX_RETRIES 时回到 ready 队列。"""
        node_id = make_uuid()
        agent_id = make_uuid()
        scheduler._running_nodes[node_id] = agent_id

        fake_node = FakeNode(node_id=node_id, retry_count=0)

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock),
            patch("app.services.dag_scheduler.remove_timeout_watch", new_callable=AsyncMock),
            patch("app.services.dag_scheduler.push_ready_node", new_callable=AsyncMock) as mock_push,
        ):
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=fake_node)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler.on_node_failed(node_id, "some error", agent_id)

        # 应该推入就绪队列
        mock_push.assert_called_once_with(str(node_id), priority=1.0)
        assert node_id not in scheduler._running_nodes

    @pytest.mark.asyncio
    async def test_permanently_fails_at_max_retries(self, scheduler: DAGScheduler):
        """达到 MAX_RETRIES 时节点标记为 failed。"""
        node_id = make_uuid()
        agent_id = make_uuid()
        scheduler._running_nodes[node_id] = agent_id

        fake_node = FakeNode(node_id=node_id, retry_count=MAX_RETRIES - 1)

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock) as mock_set_status,
            patch("app.services.dag_scheduler.remove_timeout_watch", new_callable=AsyncMock),
            patch("app.services.dag_scheduler.push_ready_node", new_callable=AsyncMock) as mock_push,
        ):
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=fake_node)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler.on_node_failed(node_id, "final error", agent_id)

        # 不应推入就绪队列
        mock_push.assert_not_called()
        # 应该设置为 failed
        mock_set_status.assert_called_with(
            scheduler.task_id, str(node_id), STATUS_FAILED
        )
        assert node_id not in scheduler._running_nodes

    @pytest.mark.asyncio
    async def test_missing_node_is_noop(self, scheduler: DAGScheduler):
        """节点不存在于DB时安全跳过。"""
        node_id = make_uuid()
        agent_id = make_uuid()

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
        ):
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=None)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            # 不应抛异常
            await scheduler.on_node_failed(node_id, "error", agent_id)


# ---------------------------------------------------------------------------
# Test: _check_timeouts
# ---------------------------------------------------------------------------


class TestCheckTimeouts:
    @pytest.mark.asyncio
    async def test_no_timeouts_is_noop(self, scheduler: DAGScheduler):
        with patch(
            "app.services.dag_scheduler.get_timed_out_nodes",
            new_callable=AsyncMock,
            return_value=[],
        ):
            # 不应抛异常
            await scheduler._check_timeouts()

    @pytest.mark.asyncio
    async def test_timeout_triggers_failure(self, scheduler: DAGScheduler):
        node_id = make_uuid()
        agent_id = make_uuid()
        scheduler._running_nodes[node_id] = agent_id

        with (
            patch(
                "app.services.dag_scheduler.get_timed_out_nodes",
                new_callable=AsyncMock,
                return_value=[str(node_id)],
            ),
            patch.object(
                scheduler, "on_node_failed", new_callable=AsyncMock
            ) as mock_fail,
        ):
            await scheduler._check_timeouts()

        mock_fail.assert_called_once_with(
            node_id=node_id,
            error="Execution timeout",
            agent_id=agent_id,
        )

    @pytest.mark.asyncio
    async def test_timeout_unknown_node_cleaned_up(self, scheduler: DAGScheduler):
        """超时节点不在 running 列表中时直接清理。"""
        node_id_str = str(make_uuid())

        with (
            patch(
                "app.services.dag_scheduler.get_timed_out_nodes",
                new_callable=AsyncMock,
                return_value=[node_id_str],
            ),
            patch(
                "app.services.dag_scheduler.remove_timeout_watch",
                new_callable=AsyncMock,
            ) as mock_remove,
        ):
            await scheduler._check_timeouts()

        mock_remove.assert_called_once_with(node_id_str)


# ---------------------------------------------------------------------------
# Test: Scheduler Registry
# ---------------------------------------------------------------------------


class TestSchedulerRegistry:
    def test_get_scheduler_returns_none_when_not_started(self):
        assert get_scheduler(make_uuid()) is None

    def test_stop_scheduler_noop_when_not_exists(self):
        # 不应抛异常
        stop_scheduler(make_uuid())

    @pytest.mark.asyncio
    async def test_start_scheduler_registers(self):
        task_id = make_uuid()

        with (
            patch.object(DAGScheduler, "run", new_callable=AsyncMock),
        ):
            scheduler = await start_scheduler(task_id)
            assert get_scheduler(task_id) is scheduler

        # 清理
        _active_schedulers.pop(task_id, None)

    @pytest.mark.asyncio
    async def test_start_scheduler_returns_existing(self):
        task_id = make_uuid()
        existing = DAGScheduler(task_id)
        _active_schedulers[task_id] = existing

        result = await start_scheduler(task_id)
        assert result is existing

        # 清理
        _active_schedulers.pop(task_id, None)


# ---------------------------------------------------------------------------
# Test: _is_dag_complete / _has_undone_nodes
# ---------------------------------------------------------------------------


class TestDagCompletion:
    @pytest.mark.asyncio
    async def test_is_complete_when_all_done(self, scheduler: DAGScheduler):
        with patch("app.services.dag_scheduler.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = None  # 没有未完成节点
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            assert await scheduler._is_dag_complete() is True

    @pytest.mark.asyncio
    async def test_is_not_complete_with_pending(self, scheduler: DAGScheduler):
        with patch("app.services.dag_scheduler.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = FakeNode()  # 有未完成节点
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            assert await scheduler._is_dag_complete() is False


# ---------------------------------------------------------------------------
# Test: _mark_task_done / _mark_task_failed
# ---------------------------------------------------------------------------


class TestMarkTask:
    @pytest.mark.asyncio
    async def test_mark_task_done(self, scheduler: DAGScheduler):
        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.communicator") as mock_comm,
        ):
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_comm.send_status_update = AsyncMock()
            mock_comm.send_task_event = AsyncMock()

            await scheduler._mark_task_done()

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_comm.send_status_update.assert_called_once()
        mock_comm.send_task_event.assert_called_once()
        assert mock_comm.send_task_event.await_args.kwargs["msg_type"] == "task_done"

    @pytest.mark.asyncio
    async def test_mark_task_failed(self, scheduler: DAGScheduler):
        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.communicator") as mock_comm,
        ):
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_comm.send_status_update = AsyncMock()
            mock_comm.send_task_event = AsyncMock()

            await scheduler._mark_task_failed("test error")

        mock_session.execute.assert_called_once()
        mock_comm.send_status_update.assert_called_once()
        mock_comm.send_task_event.assert_called_once()
        assert mock_comm.send_task_event.await_args.kwargs["payload"]["status"] == "failed"


# ---------------------------------------------------------------------------
# Test: _match_agent
# ---------------------------------------------------------------------------


class TestMatchAgent:
    @pytest.mark.asyncio
    async def test_returns_idle_agent_with_matching_role(self):
        agent = FakeAgent(role="writer")
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = agent
        mock_session.execute = AsyncMock(return_value=mock_result)

        scheduler = DAGScheduler(make_uuid())
        result = await scheduler._match_agent(mock_session, "writer")
        assert result is agent

    @pytest.mark.asyncio
    async def test_returns_none_when_no_agent_available(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        scheduler = DAGScheduler(make_uuid())
        result = await scheduler._match_agent(mock_session, "writer")
        assert result is None
