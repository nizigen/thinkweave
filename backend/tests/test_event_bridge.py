"""TaskEventBridge 单元测试"""

from __future__ import annotations

import asyncio
import uuid
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


def test_normalize_dag_update_preserves_control_payload():
    from app.services.event_bridge import normalize_task_event

    message = StreamMessage(
        stream="task:task-1:events",
        message_id="5-0",
        data={
            "msg_id": "m-control-1",
            "msg_type": "dag_update",
            "from_agent": "scheduler",
            "to_agent": "",
            "task_id": "task-1",
            "node_id": "",
            "payload": '{"control":{"status":"paused"}}',
            "timestamp": "123.0",
            "ttl": "60",
        },
    )

    event = normalize_task_event(message)

    assert event is not None
    assert event.type == "dag_update"
    assert event.payload["control"]["status"] == "paused"


def test_normalize_log_preserves_control_message():
    from app.services.event_bridge import normalize_task_event

    message = StreamMessage(
        stream="task:task-1:events",
        message_id="6-0",
        data={
            "msg_id": "m-control-2",
            "msg_type": "log",
            "from_agent": "scheduler",
            "to_agent": "",
            "task_id": "task-1",
            "node_id": "",
            "payload": '{"message":"retry accepted"}',
            "timestamp": "123.0",
            "ttl": "60",
        },
    )

    event = normalize_task_event(message)

    assert event is not None
    assert event.type == "log"
    assert event.payload["message"] == "retry accepted"


def test_normalize_malformed_event_returns_none():
    from app.services.event_bridge import normalize_task_event

    message = StreamMessage(
        stream="task:task-1:events",
        message_id="7-0",
        data={
            "msg_id": "m-bad-1",
            "msg_type": "log",
            "from_agent": "scheduler",
            "to_agent": "",
            "task_id": "task-1",
            "node_id": "",
            "payload": "{not-json",
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
    assert payload["event_id"] == "1-0"


@pytest.mark.asyncio
async def test_run_skips_malformed_event_and_broadcasts_later_valid_event(ws_manager_mock):
    from app.services.event_bridge import TaskEventBridge

    reader = AsyncMock(
        side_effect=[
            [
                StreamMessage(
                    stream="task:task-1:events",
                    message_id="1-0",
                    data={
                        "msg_id": "m-bad-1",
                        "msg_type": "log",
                        "from_agent": "writer",
                        "to_agent": "",
                        "task_id": "task-1",
                        "node_id": "node-1",
                        "payload": "{broken-json",
                        "timestamp": "123.0",
                        "ttl": "60",
                    },
                ),
                StreamMessage(
                    stream="task:task-1:events",
                    message_id="2-0",
                    data={
                        "msg_id": "m-good-1",
                        "msg_type": "status_update",
                        "from_agent": "writer",
                        "to_agent": "",
                        "task_id": "task-1",
                        "node_id": "node-1",
                        "payload": '{"status":"running"}',
                        "timestamp": "124.0",
                        "ttl": "60",
                    },
                ),
            ],
            [],
        ]
    )

    states = iter([{"ws-1"}, set()])
    ws_manager_mock.get_connections.side_effect = lambda task_id: next(states)

    bridge = TaskEventBridge(ws_manager=ws_manager_mock, reader=reader, block_ms=1)
    await bridge._run("task-1")

    ws_manager_mock.broadcast.assert_awaited_once()
    _, payload = ws_manager_mock.broadcast.await_args.args
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


@pytest.mark.asyncio
async def test_run_persists_monitor_recovery_events_before_broadcast(ws_manager_mock):
    from app.services.event_bridge import TaskEventBridge

    preview_message = StreamMessage(
        stream="task:task-1:events",
        message_id="1-0",
        data={
            "msg_id": "m-preview",
            "msg_type": "chapter_preview",
            "from_agent": "writer",
            "to_agent": "",
            "task_id": "task-1",
            "node_id": "node-1",
            "payload": '{"content":"preview body"}',
            "timestamp": "123.0",
            "ttl": "60",
        },
    )
    review_message = StreamMessage(
        stream="task:task-1:events",
        message_id="2-0",
        data={
            "msg_id": "m-review",
            "msg_type": "review_score",
            "from_agent": "reviewer",
            "to_agent": "",
            "task_id": "task-1",
            "node_id": "node-1",
            "payload": '{"score":88}',
            "timestamp": "124.0",
            "ttl": "60",
        },
    )

    reader = AsyncMock(side_effect=[[preview_message, review_message], []])
    states = iter([{"ws-1"}, {"ws-1"}, set()])
    ws_manager_mock.get_connections.side_effect = lambda task_id: next(states)

    bridge = TaskEventBridge(ws_manager=ws_manager_mock, reader=reader, block_ms=1)

    from app.services import event_bridge as event_bridge_module

    persist_mock = AsyncMock()
    original_persist = event_bridge_module.persist_monitor_recovery_event
    event_bridge_module.persist_monitor_recovery_event = persist_mock
    try:
        await bridge._run("task-1")
    finally:
        event_bridge_module.persist_monitor_recovery_event = original_persist

    assert persist_mock.await_args_list[0].kwargs["event_type"] == "chapter_preview"
    assert persist_mock.await_args_list[1].kwargs["event_type"] == "review_score"
    assert ws_manager_mock.broadcast.await_count == 2


def test_normalize_state_transition_maps_to_state_transition_event():
    from app.services.event_bridge import normalize_task_event

    message = StreamMessage(
        stream="task:task-1:events",
        message_id="8-0",
        data={
            "msg_id": "m-state-1",
            "msg_type": "state_transition",
            "from_agent": "fsm",
            "to_agent": "",
            "task_id": "task-1",
            "node_id": "",
            "payload": '{"from_state":"outline_review","to_state":"writing"}',
            "timestamp": "125.0",
            "ttl": "60",
        },
    )

    event = normalize_task_event(message)

    assert event is not None
    assert event.type == "state_transition"
    assert event.payload["from_state"] == "outline_review"
    assert event.payload["to_state"] == "writing"


@pytest.mark.asyncio
async def test_flow_controller_advances_fsm_stage_for_completed_role():
    from app.services.flow_controller import FlowController

    task = type("TaskStub", (), {})()
    task.fsm_state = "outline_review"
    task.checkpoint_data = {"k": "v"}
    session = AsyncMock()
    session.get = AsyncMock(return_value=task)

    state_store = AsyncMock()
    controller = FlowController(state_store=state_store)
    changed = await controller.on_node_completed(
        session=session,
        task_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
        node_role="writer",
    )

    assert changed is True
    state_store.transition_fsm.assert_awaited_once()
    kwargs = state_store.transition_fsm.await_args.kwargs
    assert kwargs["from_state"] == "outline_review"
    assert kwargs["to_state"] == "premise_gate"
    assert kwargs["reason"] == "flow_controller_node_completed"


@pytest.mark.asyncio
async def test_flow_controller_noop_when_stage_already_ahead():
    from app.services.flow_controller import FlowController

    task = type("TaskStub", (), {})()
    task.fsm_state = "consistency"
    task.checkpoint_data = {}
    session = AsyncMock()
    session.get = AsyncMock(return_value=task)

    state_store = AsyncMock()
    controller = FlowController(state_store=state_store)
    changed = await controller.on_node_completed(
        session=session,
        task_id=uuid.UUID("11111111-1111-4111-8111-111111111111"),
        node_role="writer",
    )

    assert changed is False
    state_store.transition_fsm.assert_not_awaited()


@pytest.mark.asyncio
async def test_replay_events_returns_normalized_payloads_with_event_id(ws_manager_mock):
    from app.services.event_bridge import TaskEventBridge

    reader = AsyncMock(
        return_value=[
            StreamMessage(
                stream="task:task-1:events",
                message_id="5-0",
                data={
                    "msg_id": "m5",
                    "msg_type": "state_transition",
                    "from_agent": "fsm",
                    "to_agent": "",
                    "task_id": "task-1",
                    "node_id": "",
                    "payload": '{"from_state":"outline","to_state":"writing"}',
                    "timestamp": "125.0",
                    "ttl": "60",
                },
            )
        ]
    )
    bridge = TaskEventBridge(ws_manager=ws_manager_mock, reader=reader, block_ms=1)
    events = await bridge.replay_events("task-1", start_from_id="4-0")

    assert len(events) == 1
    event = events[0]
    assert event["type"] == "state_transition"
    assert event["event_id"] == "5-0"
    assert event["payload"]["priority"] == "high"
