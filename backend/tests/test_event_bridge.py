"""TaskEventBridge 单元测试"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.redis_streams import StreamMessage


@pytest.fixture
def ws_manager_mock():
    manager = MagicMock()
    manager.broadcast = AsyncMock()
    manager.get_connections = MagicMock(return_value={"ws-1"})
    return manager


@pytest.mark.asyncio
async def test_connected_event_schema_serializes():
    from app.schemas.ws_event import ConnectedEvent

    event = ConnectedEvent(task_id="task-1")
    dumped = event.model_dump()

    assert dumped["type"] == "connected"
    assert dumped["task_id"] == "task-1"
    assert dumped["payload"] == {}


@pytest.mark.asyncio
async def test_ensure_started_is_idempotent(ws_manager_mock):
    from app.services.event_bridge import TaskEventBridge

    blocker = asyncio.Event()
    bridge = TaskEventBridge(ws_manager=ws_manager_mock)

    async def fake_run(task_id: str, *, start_from_id: str = "$") -> None:
        await blocker.wait()

    bridge._run = fake_run  # type: ignore[method-assign]

    first = await bridge.ensure_started("task-1")
    second = await bridge.ensure_started("task-1")

    assert first is True
    assert second is False
    assert len(bridge._tasks) == 1

    await bridge.stop("task-1")
    blocker.set()


@pytest.mark.asyncio
async def test_ensure_started_is_concurrency_safe(ws_manager_mock):
    from app.services.event_bridge import TaskEventBridge

    blocker = asyncio.Event()
    bridge = TaskEventBridge(ws_manager=ws_manager_mock)

    async def fake_run(task_id: str, *, start_from_id: str = "$") -> None:
        await blocker.wait()

    bridge._run = fake_run  # type: ignore[method-assign]

    results = await asyncio.gather(
        *(bridge.ensure_started("task-1") for _ in range(8))
    )

    assert results.count(True) == 1
    assert results.count(False) == 7
    assert len(bridge._tasks) == 1

    await bridge.stop("task-1")
    blocker.set()


def test_normalize_status_update_maps_to_node_update():
    from app.services.event_bridge import normalize_task_event

    message = StreamMessage(
        stream="task:task-1:events",
        message_id="1-0",
        data={
            "msg_id": "m1",
            "msg_type": "status_update",
            "from_agent": "writer",
            "to_agent": "",
            "task_id": "task-1",
            "node_id": "node-1",
            "payload": '{"status":"running"}',
            "timestamp": "123.0",
            "ttl": "60",
        },
    )

    event = normalize_task_event(message)

    assert event is not None
    assert event.type == "node_update"
    assert event.task_id == "task-1"
    assert event.node_id == "node-1"
    assert event.payload["status"] == "running"


def test_normalize_unknown_type_returns_none():
    from app.services.event_bridge import normalize_task_event

    message = StreamMessage(
        stream="task:task-1:events",
        message_id="1-0",
        data={
            "msg_id": "m1",
            "msg_type": "mystery",
            "from_agent": "writer",
            "to_agent": "",
            "task_id": "task-1",
            "node_id": "node-1",
            "payload": '{}',
            "timestamp": "123.0",
            "ttl": "60",
        },
    )

    assert normalize_task_event(message) is None


@pytest.mark.asyncio
async def test_run_broadcasts_normalized_events(ws_manager_mock):
    from app.services.event_bridge import TaskEventBridge

    reader = AsyncMock(
        side_effect=[
            [
                StreamMessage(
                    stream="task:task-1:events",
                    message_id="1-0",
                    data={
                        "msg_id": "m1",
                        "msg_type": "status_update",
                        "from_agent": "writer",
                        "to_agent": "",
                        "task_id": "task-1",
                        "node_id": "node-1",
                        "payload": '{"status":"running"}',
                        "timestamp": "123.0",
                        "ttl": "60",
                    },
                )
            ],
            [],
        ]
    )

    states = iter([{"ws-1"}, set()])
    ws_manager_mock.get_connections.side_effect = lambda task_id: next(states)

    bridge = TaskEventBridge(ws_manager=ws_manager_mock, reader=reader, block_ms=1)
    await bridge._run("task-1")

    ws_manager_mock.broadcast.assert_awaited_once()
    task_id, payload = ws_manager_mock.broadcast.await_args.args
    assert task_id == "task-1"
    assert payload["type"] == "node_update"


@pytest.mark.asyncio
async def test_stop_cancels_reader_and_cleans_registry(ws_manager_mock):
    from app.services.event_bridge import TaskEventBridge

    blocker = asyncio.Event()
    bridge = TaskEventBridge(ws_manager=ws_manager_mock)

    async def fake_run(task_id: str, *, start_from_id: str = "$") -> None:
        await blocker.wait()

    bridge._run = fake_run  # type: ignore[method-assign]

    await bridge.ensure_started("task-1")
    assert "task-1" in bridge._tasks

    await bridge.stop("task-1")

    assert "task-1" not in bridge._tasks


@pytest.mark.asyncio
async def test_ensure_started_passes_start_cursor_to_reader_task(ws_manager_mock):
    from app.services.event_bridge import TaskEventBridge

    blocker = asyncio.Event()
    bridge = TaskEventBridge(ws_manager=ws_manager_mock)
    captured: dict[str, str] = {}

    async def fake_run(task_id: str, *, start_from_id: str = "$") -> None:
        captured["task_id"] = task_id
        captured["start_from_id"] = start_from_id
        await blocker.wait()

    bridge._run = fake_run  # type: ignore[method-assign]

    await bridge.ensure_started("task-1", start_from_id="42-0")
    await asyncio.sleep(0)

    assert captured == {"task_id": "task-1", "start_from_id": "42-0"}

    await bridge.stop("task-1")
    blocker.set()


@pytest.mark.asyncio
async def test_run_recovers_from_transient_reader_failure(ws_manager_mock):
    from app.services.event_bridge import TaskEventBridge

    message = StreamMessage(
        stream="task:task-1:events",
        message_id="1-0",
        data={
            "msg_id": "m1",
            "msg_type": "status_update",
            "from_agent": "writer",
            "to_agent": "",
            "task_id": "task-1",
            "node_id": "node-1",
            "payload": '{"status":"running"}',
            "timestamp": "123.0",
            "ttl": "60",
        },
    )

    reader = AsyncMock(side_effect=[RuntimeError("redis timeout"), [message], []])
    states = iter([{"ws-1"}, {"ws-1"}, {"ws-1"}, set()])
    ws_manager_mock.get_connections.side_effect = lambda task_id: next(states)

    bridge = TaskEventBridge(
        ws_manager=ws_manager_mock,
        reader=reader,
        block_ms=1,
        retry_backoff_base=0.001,
        retry_backoff_max=0.001,
    )
    await bridge._run("task-1")

    ws_manager_mock.broadcast.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_retries_failed_broadcast_without_losing_event(ws_manager_mock):
    from app.services.event_bridge import TaskEventBridge

    message = StreamMessage(
        stream="task:task-1:events",
        message_id="1-0",
        data={
            "msg_id": "m1",
            "msg_type": "status_update",
            "from_agent": "writer",
            "to_agent": "",
            "task_id": "task-1",
            "node_id": "node-1",
            "payload": '{"status":"running"}',
            "timestamp": "123.0",
            "ttl": "60",
        },
    )

    reader = AsyncMock(side_effect=[[message], [message], []])
    ws_manager_mock.broadcast.side_effect = [RuntimeError("socket hiccup"), None]
    states = iter([{"ws-1"}, {"ws-1"}, {"ws-1"}, set()])
    ws_manager_mock.get_connections.side_effect = lambda task_id: next(states)

    bridge = TaskEventBridge(
        ws_manager=ws_manager_mock,
        reader=reader,
        block_ms=1,
        retry_backoff_base=0.001,
        retry_backoff_max=0.001,
    )
    await bridge._run("task-1")

    assert ws_manager_mock.broadcast.await_count == 2
