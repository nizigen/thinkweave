"""Tests for communicator.py — 业务层消息收发

使用 mock 模拟 redis_streams 底层调用和 DB session。
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.communicator import (
    AGENT_INBOX_GROUP,
    TASK_EVENTS_GROUP,
    ack_agent_message,
    ack_task_event,
    consume_agent_inbox,
    consume_task_events,
    send_status_update,
    send_system_log,
    send_task_assignment,
    send_task_result,
)
from app.services.redis_streams import MessageEnvelope, StreamMessage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_persist():
    """所有测试都 mock 掉 DB 持久化，避免需要真实数据库。"""
    with patch("app.services.communicator._persist_message", new_callable=AsyncMock) as m:
        yield m


@pytest.fixture()
def _mock_streams():
    """Mock redis_streams 底层函数。"""
    with (
        patch("app.services.communicator.ensure_consumer_group", new_callable=AsyncMock) as ecg,
        patch("app.services.communicator.xadd", new_callable=AsyncMock, return_value="100-0") as xa,
        patch("app.services.communicator.xreadgroup", new_callable=AsyncMock, return_value=[]) as xrg,
        patch("app.services.communicator.xack", new_callable=AsyncMock, return_value=1) as xk,
    ):
        yield {"ensure_consumer_group": ecg, "xadd": xa, "xreadgroup": xrg, "xack": xk}


# ---------------------------------------------------------------------------
# send_task_assignment
# ---------------------------------------------------------------------------


class TestSendTaskAssignment:
    @pytest.mark.asyncio
    async def test_sends_to_agent_inbox(self, _mock_streams, _mock_persist):
        mid = await send_task_assignment(
            agent_id="agent-1",
            task_id="task-1",
            node_id="node-1",
            payload={"chapter": 1},
        )
        assert mid == "100-0"

        # ensure_consumer_group called for agent inbox
        _mock_streams["ensure_consumer_group"].assert_awaited_once()
        call_args = _mock_streams["ensure_consumer_group"].call_args
        assert "agent:agent-1:inbox" in call_args[0]

        # xadd called with correct stream
        _mock_streams["xadd"].assert_awaited_once()
        stream_arg = _mock_streams["xadd"].call_args[0][0]
        assert stream_arg == "agent:agent-1:inbox"

        # envelope has correct type
        envelope_arg = _mock_streams["xadd"].call_args[0][1]
        assert envelope_arg.msg_type == "task_assign"
        assert envelope_arg.to_agent == "agent-1"

        # persist called
        _mock_persist.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_persist_false_skips_db(self, _mock_streams, _mock_persist):
        await send_task_assignment(
            agent_id="a1", task_id="t1", node_id="n1", persist=False,
        )
        _mock_persist.assert_not_awaited()


# ---------------------------------------------------------------------------
# send_task_result
# ---------------------------------------------------------------------------


class TestSendTaskResult:
    @pytest.mark.asyncio
    async def test_sends_to_task_events(self, _mock_streams, _mock_persist):
        mid = await send_task_result(
            task_id="task-1",
            node_id="node-1",
            from_agent="writer_1",
            result={"text": "chapter content"},
        )
        assert mid == "100-0"

        stream_arg = _mock_streams["xadd"].call_args[0][0]
        assert stream_arg == "task:task-1:events"

        envelope_arg = _mock_streams["xadd"].call_args[0][1]
        assert envelope_arg.msg_type == "task_result"
        assert envelope_arg.from_agent == "writer_1"

    @pytest.mark.asyncio
    async def test_persist_true_by_default(self, _mock_streams, _mock_persist):
        await send_task_result(
            task_id="t1", node_id="n1", from_agent="w1", result={},
        )
        _mock_persist.assert_awaited_once()


# ---------------------------------------------------------------------------
# send_status_update
# ---------------------------------------------------------------------------


class TestSendStatusUpdate:
    @pytest.mark.asyncio
    async def test_sends_status_update(self, _mock_streams):
        mid = await send_status_update(
            task_id="t1", node_id="n1", status="running",
        )
        assert mid == "100-0"

        envelope_arg = _mock_streams["xadd"].call_args[0][1]
        assert envelope_arg.msg_type == "status_update"
        assert envelope_arg.payload["status"] == "running"

    @pytest.mark.asyncio
    async def test_includes_extra(self, _mock_streams):
        await send_status_update(
            task_id="t1", status="done", extra={"word_count": 5000},
        )
        envelope_arg = _mock_streams["xadd"].call_args[0][1]
        assert envelope_arg.payload["word_count"] == 5000


# ---------------------------------------------------------------------------
# send_system_log
# ---------------------------------------------------------------------------


class TestSendSystemLog:
    @pytest.mark.asyncio
    async def test_sends_to_system_logs(self, _mock_streams):
        mid = await send_system_log(
            level="warning", message="node timeout", task_id="t1",
        )
        assert mid == "100-0"

        stream_arg = _mock_streams["xadd"].call_args[0][0]
        assert stream_arg == "system:logs"

        envelope_arg = _mock_streams["xadd"].call_args[0][1]
        assert envelope_arg.payload["level"] == "warning"
        assert envelope_arg.payload["message"] == "node timeout"


# ---------------------------------------------------------------------------
# consume / ack
# ---------------------------------------------------------------------------


class TestConsumeAgentInbox:
    @pytest.mark.asyncio
    async def test_calls_xreadgroup(self, _mock_streams):
        _mock_streams["xreadgroup"].return_value = [
            StreamMessage(stream="agent:a1:inbox", message_id="1-0", data={"msg_type": "task_assign"}),
        ]
        msgs = await consume_agent_inbox("a1", "consumer-1", count=5, block=1000)
        assert len(msgs) == 1

        _mock_streams["xreadgroup"].assert_awaited_once()
        call_args = _mock_streams["xreadgroup"].call_args
        assert call_args[0][0] == AGENT_INBOX_GROUP
        assert call_args[0][1] == "consumer-1"


class TestAckAgentMessage:
    @pytest.mark.asyncio
    async def test_delegates_to_xack(self, _mock_streams):
        result = await ack_agent_message("a1", "1-0")
        assert result == 1
        _mock_streams["xack"].assert_awaited_once()


class TestConsumeTaskEvents:
    @pytest.mark.asyncio
    async def test_calls_xreadgroup(self, _mock_streams):
        await consume_task_events("t1", "ws-handler-1")
        _mock_streams["xreadgroup"].assert_awaited_once()


class TestAckTaskEvent:
    @pytest.mark.asyncio
    async def test_delegates_to_xack(self, _mock_streams):
        result = await ack_task_event("t1", "1-0")
        assert result == 1


# ---------------------------------------------------------------------------
# Heartbeat 模块
# ---------------------------------------------------------------------------


class TestHeartbeat:
    @pytest.mark.asyncio
    async def test_send_heartbeat_updates_state(self):
        with patch("app.services.heartbeat.set_agent_state", new_callable=AsyncMock) as mock_set:
            from app.services.heartbeat import send_heartbeat
            await send_heartbeat("agent-1", status="busy", current_task="t1")
            mock_set.assert_awaited_once()
            state_arg = mock_set.call_args[0][1]
            assert state_arg["status"] == "busy"
            assert state_arg["current_task"] == "t1"
            assert "last_heartbeat" in state_arg

    @pytest.mark.asyncio
    async def test_check_agent_alive_true(self):
        import time
        now = str(time.time())
        with patch("app.services.heartbeat.get_agent_state", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"status": "idle", "last_heartbeat": now}
            from app.services.heartbeat import check_agent_alive
            assert await check_agent_alive("a1") is True

    @pytest.mark.asyncio
    async def test_check_agent_alive_false_expired(self):
        old_time = str(1000.0)  # way in the past
        with patch("app.services.heartbeat.get_agent_state", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"status": "idle", "last_heartbeat": old_time}
            from app.services.heartbeat import check_agent_alive
            assert await check_agent_alive("a1") is False

    @pytest.mark.asyncio
    async def test_check_agent_alive_false_no_state(self):
        with patch("app.services.heartbeat.get_agent_state", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {}
            from app.services.heartbeat import check_agent_alive
            assert await check_agent_alive("a1") is False

    @pytest.mark.asyncio
    async def test_find_expired_agents(self):
        import time
        now = str(time.time())
        old = str(1000.0)
        # Mock pipeline-based batch query
        states_list = [
            {"last_heartbeat": now},   # a1: alive
            {"last_heartbeat": old},   # a2: expired
            {},                         # a3: no state
        ]

        mock_pipe = MagicMock()
        mock_pipe.hgetall = MagicMock(return_value=mock_pipe)
        mock_pipe.execute = AsyncMock(return_value=states_list)

        with patch("app.services.heartbeat.redis_client") as mock_redis:
            mock_redis.pipeline = MagicMock(return_value=mock_pipe)
            from app.services.heartbeat import find_expired_agents
            expired = await find_expired_agents(["a1", "a2", "a3"])
            assert "a2" in expired
            assert "a3" in expired
            assert "a1" not in expired


# ---------------------------------------------------------------------------
# Timeout Monitor
# ---------------------------------------------------------------------------


class TestTimeoutMonitor:
    @pytest.mark.asyncio
    async def test_run_detects_and_calls_callback(self):
        import asyncio

        callback = AsyncMock()
        stop = asyncio.Event()

        with (
            patch("app.services.timeout_monitor.get_timed_out_nodes", new_callable=AsyncMock) as mock_get,
            patch("app.services.timeout_monitor.remove_timeout_watch", new_callable=AsyncMock),
        ):
            # 第一次扫描返回超时节点，第二次停止
            call_count = 0
            async def side_effect(**kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return ["n1", "n2"]
                stop.set()
                return []

            mock_get.side_effect = side_effect

            from app.services.timeout_monitor import run_timeout_monitor
            await run_timeout_monitor(callback, poll_interval=0.05, stop_event=stop)

            assert callback.await_count == 2  # n1 and n2
            callback.assert_any_await("n1")
            callback.assert_any_await("n2")

    @pytest.mark.asyncio
    async def test_watch_and_unwatch(self):
        with (
            patch("app.services.timeout_monitor.add_timeout_watch", new_callable=AsyncMock) as mock_add,
            patch("app.services.timeout_monitor.remove_timeout_watch", new_callable=AsyncMock) as mock_rm,
        ):
            from app.services.timeout_monitor import watch_node, unwatch_node
            await watch_node("n1", timeout_seconds=60)
            mock_add.assert_awaited_once()

            await unwatch_node("n1")
            mock_rm.assert_awaited_once_with("n1")
