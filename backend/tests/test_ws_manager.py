"""WebSocketManager 单元测试"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ws_manager import WebSocketManager, ConnectionLimitError, MAX_CONNECTIONS_PER_TASK


@pytest.fixture
def manager():
    return WebSocketManager()


@pytest.fixture
def mock_ws():
    ws = MagicMock()
    ws.send_text = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_connect_registers_websocket(manager, mock_ws):
    task_id = "task-001"
    await manager.connect(task_id, mock_ws)
    assert mock_ws in manager.get_connections(task_id)


@pytest.mark.asyncio
async def test_pending_connection_not_visible_until_activated(manager, mock_ws):
    task_id = "task-001"
    await manager.connect(task_id, mock_ws, ready=False)
    assert mock_ws not in manager.get_connections(task_id)
    manager.activate(task_id, mock_ws)
    assert mock_ws in manager.get_connections(task_id)


@pytest.mark.asyncio
async def test_disconnect_removes_websocket(manager, mock_ws):
    task_id = "task-001"
    await manager.connect(task_id, mock_ws)
    manager.disconnect(task_id, mock_ws)
    assert mock_ws not in manager.get_connections(task_id)


@pytest.mark.asyncio
async def test_disconnect_removes_pending_websocket(manager, mock_ws):
    task_id = "task-001"
    await manager.connect(task_id, mock_ws, ready=False)
    manager.disconnect(task_id, mock_ws)
    assert mock_ws not in manager.get_connections(task_id)


@pytest.mark.asyncio
async def test_disconnect_unknown_task_no_error(manager, mock_ws):
    """Disconnecting a WS that was never registered should not raise."""
    manager.disconnect("nonexistent", mock_ws)  # should not raise


@pytest.mark.asyncio
async def test_disconnect_cleans_pong_state(manager, mock_ws):
    """Disconnect must remove the ws id from _pong_received."""
    task_id = "task-001"
    await manager.connect(task_id, mock_ws)
    manager.record_pong(mock_ws)
    assert id(mock_ws) in manager._pong_received
    manager.disconnect(task_id, mock_ws)
    assert id(mock_ws) not in manager._pong_received


@pytest.mark.asyncio
async def test_broadcast_sends_to_all_connections(manager):
    task_id = "task-001"
    ws1, ws2 = MagicMock(), MagicMock()
    ws1.send_text = AsyncMock()
    ws2.send_text = AsyncMock()
    await manager.connect(task_id, ws1)
    await manager.connect(task_id, ws2)
    await manager.broadcast(task_id, {"type": "test", "data": "hello"})
    ws1.send_text.assert_awaited_once()
    ws2.send_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_broadcast_skips_failed_connection(manager):
    """If one connection raises on send, others still receive the message."""
    task_id = "task-001"
    ws_ok = MagicMock()
    ws_ok.send_text = AsyncMock()
    ws_fail = MagicMock()
    ws_fail.send_text = AsyncMock(side_effect=Exception("broken pipe"))
    await manager.connect(task_id, ws_ok)
    await manager.connect(task_id, ws_fail)
    await manager.broadcast(task_id, {"type": "test"})  # should not raise
    ws_ok.send_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_broadcast_no_connections_is_noop(manager):
    """Broadcasting to a task_id with zero connections should be a no-op."""
    await manager.broadcast("nonexistent", {"type": "test"})  # should not raise


@pytest.mark.asyncio
async def test_broadcast_skips_pending_connections(manager):
    task_id = "task-001"
    ws_pending = MagicMock()
    ws_pending.send_text = AsyncMock()
    await manager.connect(task_id, ws_pending, ready=False)
    await manager.broadcast(task_id, {"type": "test"})
    ws_pending.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_multiple_tasks_isolated(manager):
    """Connections for different task_ids must not receive each other's messages."""
    ws_a, ws_b = MagicMock(), MagicMock()
    ws_a.send_text = AsyncMock()
    ws_b.send_text = AsyncMock()
    await manager.connect("task-A", ws_a)
    await manager.connect("task-B", ws_b)
    await manager.broadcast("task-A", {"type": "test"})
    ws_a.send_text.assert_awaited_once()
    ws_b.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_connections_no_leak(manager):
    """get_connections on unknown task_id must not pollute the defaultdict."""
    result = manager.get_connections("never-seen")
    assert result == set()
    assert "never-seen" not in manager._connections


@pytest.mark.asyncio
async def test_heartbeat_sends_ping(manager, mock_ws):
    """Heartbeat must send {type: ping} within the first interval."""
    task_id = "task-hb"
    await manager.connect(task_id, mock_ws)
    task = asyncio.create_task(
        manager.run_heartbeat(mock_ws, task_id, ping_interval=0.05, timeout=0.2)
    )
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    calls = [call.args[0] for call in mock_ws.send_text.await_args_list]
    assert any('"ping"' in c for c in calls)


@pytest.mark.asyncio
async def test_heartbeat_disconnects_on_timeout(manager):
    """If no pong received within timeout, ws.close() must be called."""
    task_id = "task-timeout"
    ws = MagicMock()
    ws.send_text = AsyncMock()
    ws.close = AsyncMock()
    await manager.connect(task_id, ws)
    await manager.run_heartbeat(ws, task_id, ping_interval=0.05, timeout=0.1)
    ws.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_heartbeat_survives_when_pong_received(manager):
    """Calling record_pong within timeout window must prevent disconnect."""
    ws = MagicMock()
    ws.send_text = AsyncMock()
    ws.close = AsyncMock()
    task_id = "task-pong"
    await manager.connect(task_id, ws)
    task = asyncio.create_task(
        manager.run_heartbeat(ws, task_id, ping_interval=0.05, timeout=0.15)
    )
    await asyncio.sleep(0.06)  # wait for ping
    manager.record_pong(ws)  # simulate client pong
    await asyncio.sleep(0.12)  # wait past original timeout
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    ws.close.assert_not_awaited()  # should NOT have been closed


@pytest.mark.asyncio
async def test_connect_rejects_when_per_task_limit_exceeded(manager):
    """Exceeding MAX_CONNECTIONS_PER_TASK must raise ConnectionLimitError."""
    task_id = "task-limit"
    for _ in range(MAX_CONNECTIONS_PER_TASK):
        ws = MagicMock()
        await manager.connect(task_id, ws)
    extra_ws = MagicMock()
    with pytest.raises(ConnectionLimitError):
        await manager.connect(task_id, extra_ws)
