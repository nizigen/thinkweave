"""Step 7.3 WebSocket 集成测试 — 断线重连、多客户端、压力、DAG回退"""
from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ws_manager import WebSocketManager


def _make_ws(send_raises: Exception | None = None) -> MagicMock:
    ws = MagicMock()
    if send_raises:
        ws.send_text = AsyncMock(side_effect=send_raises)
    else:
        ws.send_text = AsyncMock()
    return ws


# ---------------------------------------------------------------------------
# 断线重连
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestWSReconnect:
    async def test_connect_then_disconnect_clears_state(self):
        """connect 后 disconnect，manager 不再持有该 ws"""
        mgr = WebSocketManager()
        task_id = str(uuid.uuid4())
        ws = _make_ws()

        await mgr.connect(task_id, ws)
        assert ws in mgr.get_connections(task_id)

        mgr.disconnect(task_id, ws)
        assert ws not in mgr.get_connections(task_id)

    async def test_reconnect_after_disconnect_works(self):
        """同一 ws 对象 disconnect 后可以重新 connect"""
        mgr = WebSocketManager()
        task_id = str(uuid.uuid4())
        ws = _make_ws()

        await mgr.connect(task_id, ws)
        mgr.disconnect(task_id, ws)
        await mgr.connect(task_id, ws)
        assert ws in mgr.get_connections(task_id)

    async def test_multiple_reconnects_allowed(self):
        """多次断线重连都正常"""
        mgr = WebSocketManager()
        task_id = str(uuid.uuid4())
        ws = _make_ws()

        for _ in range(5):
            await mgr.connect(task_id, ws)
            mgr.disconnect(task_id, ws)

        # 最终状态应为断开
        assert ws not in mgr.get_connections(task_id)


# ---------------------------------------------------------------------------
# 多客户端订阅
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestWSMultiClient:
    async def test_multiple_clients_same_task(self):
        """多个 ws 连接同一 task_id 都能正常追踪"""
        mgr = WebSocketManager()
        task_id = str(uuid.uuid4())
        ws1, ws2, ws3 = _make_ws(), _make_ws(), _make_ws()

        await mgr.connect(task_id, ws1)
        await mgr.connect(task_id, ws2)
        await mgr.connect(task_id, ws3)

        conns = mgr.get_connections(task_id)
        assert ws1 in conns
        assert ws2 in conns
        assert ws3 in conns

    async def test_broadcast_reaches_all_subscribers(self):
        """broadcast 将消息发送给所有已连接的 ws"""
        mgr = WebSocketManager()
        task_id = str(uuid.uuid4())
        ws1, ws2 = _make_ws(), _make_ws()

        await mgr.connect(task_id, ws1)
        await mgr.connect(task_id, ws2)

        msg = {"type": "status_update", "status": "writing"}
        await mgr.broadcast(task_id, msg)

        payload = json.dumps(msg, ensure_ascii=False)
        ws1.send_text.assert_called_once_with(payload)
        ws2.send_text.assert_called_once_with(payload)

    async def test_disconnect_one_client_others_unaffected(self):
        """断开一个客户端不影响其他客户端"""
        mgr = WebSocketManager()
        task_id = str(uuid.uuid4())
        ws1, ws2 = _make_ws(), _make_ws()

        await mgr.connect(task_id, ws1)
        await mgr.connect(task_id, ws2)
        mgr.disconnect(task_id, ws1)

        assert ws1 not in mgr.get_connections(task_id)
        assert ws2 in mgr.get_connections(task_id)


# ---------------------------------------------------------------------------
# 压力测试
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestWSPressure:
    async def test_broadcast_large_message_count(self):
        """快速广播 500 条消息，所有消息都被发送"""
        mgr = WebSocketManager()
        task_id = str(uuid.uuid4())
        ws = _make_ws()
        await mgr.connect(task_id, ws)

        for i in range(500):
            await mgr.broadcast(task_id, {"type": "log", "seq": i, "text": f"log line {i}"})

        assert ws.send_text.call_count == 500

    async def test_broadcast_auto_removes_dead_connection(self):
        """send_text 抛异常时，broadcast 自动移除死连接"""
        mgr = WebSocketManager()
        task_id = str(uuid.uuid4())
        dead_ws = _make_ws(send_raises=RuntimeError("connection closed"))
        live_ws = _make_ws()

        await mgr.connect(task_id, dead_ws)
        await mgr.connect(task_id, live_ws)

        await mgr.broadcast(task_id, {"type": "ping"})

        # 死连接被自动移除
        assert dead_ws not in mgr.get_connections(task_id)
        # 活连接不受影响
        assert live_ws in mgr.get_connections(task_id)


# ---------------------------------------------------------------------------
# DAG 动态更新（FSM 回退）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestWSDAGUpdate:
    async def test_broadcast_dag_node_status_change(self):
        """FSM 回退时，DAG 节点状态变更通过 broadcast 通知所有客户端"""
        mgr = WebSocketManager()
        task_id = str(uuid.uuid4())
        ws = _make_ws()
        await mgr.connect(task_id, ws)

        # 模拟章节审查不通过，节点回退到 pending
        msg = {
            "type": "node_status",
            "node_id": "chapter-2",
            "status": "pending",
            "reason": "review_failed",
        }
        await mgr.broadcast(task_id, msg)

        payload = json.dumps(msg, ensure_ascii=False)
        ws.send_text.assert_called_once_with(payload)

    async def test_dag_update_after_reconnect(self):
        """重连后广播的 DAG 更新客户端能收到"""
        mgr = WebSocketManager()
        task_id = str(uuid.uuid4())
        ws = _make_ws()

        await mgr.connect(task_id, ws)
        mgr.disconnect(task_id, ws)
        await mgr.connect(task_id, ws)

        msg = {"type": "dag_sync", "nodes": [{"id": "n1", "status": "done"}]}
        await mgr.broadcast(task_id, msg)

        ws.send_text.assert_called_once_with(json.dumps(msg, ensure_ascii=False))
