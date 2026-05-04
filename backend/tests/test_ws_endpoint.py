"""WebSocket 端点集成测试"""

import asyncio
import json
import time
import uuid

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi import WebSocketDisconnect, status
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.routers.ws import MAX_WS_MESSAGE_SIZE, websocket_task

_SENTINEL = object()
_AUTH_HEADERS = {"Authorization": "Bearer test"}


@pytest.fixture
def client():
    return TestClient(app)


async def _fake_session():
    """Async generator that yields a mock session (no DB needed)."""
    yield MagicMock()


def _mock_task(task_id="task-001", owner_id="user-1"):
    """Create a mock Task object."""
    task = MagicMock()
    task.id = task_id
    task.owner_id = owner_id
    return task


def _auth_and_task_patches(task_return=_SENTINEL, user_id="user-1"):
    """Return a stack of patches for auth + session + task lookup."""
    if task_return is _SENTINEL:
        task_return = _mock_task()
    return [
        patch("app.routers.ws.get_session", _fake_session),
        patch(
            "app.routers.ws.get_task_exists",
            new_callable=AsyncMock,
            return_value=task_return,
        ),
        patch(
            "app.routers.ws._authenticate_ws_token",
            return_value=user_id,
        ),
    ]


def _assert_policy_violation(client: TestClient, path: str, *, headers: dict[str, str] | None = None) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(path, headers=headers or {}):
            pass
    assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION


def test_ws_rejects_unknown_task(client):
    """Connecting to a non-existent task_id must close the connection."""
    patches = _auth_and_task_patches(task_return=None)
    with patches[0], patches[1], patches[2]:
        _assert_policy_violation(
            client,
            "/ws/task/00000000-0000-0000-0000-000000000001",
            headers=_AUTH_HEADERS,
        )


def test_ws_rejects_invalid_uuid(client):
    """Connecting with a non-UUID task_id must close the connection."""
    _assert_policy_violation(client, "/ws/task/not-a-uuid?token=test")


def test_ws_rejects_unauthenticated(client):
    """Connecting without valid token must close the connection."""
    with patch("app.routers.ws._authenticate_ws_token", return_value=""):
        _assert_policy_violation(
            client,
            "/ws/task/00000000-0000-0000-0000-000000000001",
        )


def test_ws_accepts_known_task(client):
    """Connecting to a known task_id should succeed and receive 'connected'."""
    patches = _auth_and_task_patches()
    with patches[0], patches[1], patches[2]:
        with (
            patch("app.routers.ws.ws_manager") as mock_mgr,
            patch("app.routers.ws.event_bridge") as mock_bridge,
            patch("app.routers.ws.get_task_event_cursor", new_callable=AsyncMock, return_value="7-0"),
        ):
            mock_mgr.connect = AsyncMock()
            mock_mgr.activate = MagicMock()
            mock_mgr.disconnect = MagicMock()
            mock_mgr.get_connections = MagicMock(return_value={"ws-1"})
            mock_mgr.run_heartbeat = AsyncMock()
            mock_bridge.ensure_started = AsyncMock()
            mock_bridge.stop = AsyncMock()
            with client.websocket_connect(
                "/ws/task/00000000-0000-0000-0000-000000000001",
                headers=_AUTH_HEADERS,
            ) as ws:
                data = ws.receive_json()
                assert data["type"] == "connected"
                assert data["task_id"] == "00000000-0000-0000-0000-000000000001"
            mock_bridge.ensure_started.assert_awaited_once_with(
                "00000000-0000-0000-0000-000000000001",
                start_from_id="7-0",
            )


def test_ws_pong_handled(client):
    """Sending {type: pong} must call ws_manager.record_pong."""
    patches = _auth_and_task_patches()
    with patches[0], patches[1], patches[2]:
        with (
            patch("app.routers.ws.ws_manager") as mock_mgr,
            patch("app.routers.ws.event_bridge") as mock_bridge,
            patch("app.routers.ws.get_task_event_cursor", new_callable=AsyncMock, return_value="7-0"),
        ):
            mock_mgr.connect = AsyncMock()
            mock_mgr.activate = MagicMock()
            mock_mgr.disconnect = MagicMock()
            mock_mgr.get_connections = MagicMock(return_value={"ws-1"})
            mock_mgr.record_pong = MagicMock()
            mock_mgr.run_heartbeat = AsyncMock()
            mock_bridge.ensure_started = AsyncMock()
            mock_bridge.stop = AsyncMock()
            with client.websocket_connect(
                "/ws/task/00000000-0000-0000-0000-000000000001",
                headers=_AUTH_HEADERS,
            ) as ws:
                ws.receive_json()  # consume 'connected'
                ws.send_json({"type": "pong"})
                time.sleep(0.05)
            mock_mgr.record_pong.assert_called_once()


def test_ws_rejects_non_owner(client):
    """Connecting to a task owned by another user must close the connection."""
    task = _mock_task(owner_id="other-user")
    patches = _auth_and_task_patches(task_return=task, user_id="attacker")
    with patches[0], patches[1], patches[2]:
        with patch("app.routers.ws._parse_admin_users", return_value=set()):
            _assert_policy_violation(
                client,
                "/ws/task/00000000-0000-0000-0000-000000000001",
                headers=_AUTH_HEADERS,
            )


def test_ws_rejects_ownerless_task(client):
    """Ownerless tasks should fail closed for non-admin websocket access."""
    task = _mock_task(owner_id=None)
    patches = _auth_and_task_patches(task_return=task, user_id="user-1")
    with patches[0], patches[1], patches[2]:
        with patch("app.routers.ws._parse_admin_users", return_value=set()):
            _assert_policy_violation(
                client,
                "/ws/task/00000000-0000-0000-0000-000000000001",
                headers=_AUTH_HEADERS,
            )


def test_ws_rejects_query_token_by_default(client):
    """Query-string token fallback is disabled unless explicitly enabled."""
    task = _mock_task()
    with (
        patch("app.routers.ws.get_session", _fake_session),
        patch(
            "app.routers.ws.get_task_exists",
            new_callable=AsyncMock,
            return_value=task,
        ),
        patch(
            "app.routers.ws._authenticate_ws_token",
            side_effect=lambda token: "user-1" if token == "test" else "",
        ),
    ):
        _assert_policy_violation(
            client,
            "/ws/task/00000000-0000-0000-0000-000000000001?token=test",
        )


def test_ws_accepts_configured_origin(client):
    """Configured WS origins should not be limited to localhost only."""
    patches = _auth_and_task_patches()
    original = settings.cors_allow_origins
    settings.cors_allow_origins = "http://localhost:5173,https://staging.example.com"
    try:
        with patches[0], patches[1], patches[2]:
            with (
                patch("app.routers.ws.ws_manager") as mock_mgr,
                patch("app.routers.ws.event_bridge") as mock_bridge,
                patch("app.routers.ws.get_task_event_cursor", new_callable=AsyncMock, return_value="7-0"),
            ):
                mock_mgr.connect = AsyncMock()
                mock_mgr.activate = MagicMock()
                mock_mgr.disconnect = MagicMock()
                mock_mgr.get_connections = MagicMock(return_value={"ws-1"})
                mock_mgr.run_heartbeat = AsyncMock()
                mock_bridge.ensure_started = AsyncMock()
                mock_bridge.stop = AsyncMock()
                with client.websocket_connect(
                    "/ws/task/00000000-0000-0000-0000-000000000001",
                    headers={"origin": "https://staging.example.com", **_AUTH_HEADERS},
                ) as ws:
                    data = ws.receive_json()
                    assert data["type"] == "connected"
    finally:
        settings.cors_allow_origins = original


def test_ws_rejects_disallowed_origin(client):
    """Origins outside configured allowlist must be rejected."""
    patches = _auth_and_task_patches()
    original = settings.cors_allow_origins
    settings.cors_allow_origins = "https://app.example.com"
    try:
        with patches[0], patches[1], patches[2]:
            _assert_policy_violation(
                client,
                "/ws/task/00000000-0000-0000-0000-000000000001",
                headers={"origin": "https://evil.example.com", **_AUTH_HEADERS},
            )
    finally:
        settings.cors_allow_origins = original


def test_ws_accepts_same_origin_even_if_not_explicitly_allowlisted(client):
    """Same-origin websocket handshake should pass without static allowlist entry."""
    patches = _auth_and_task_patches()
    original = settings.cors_allow_origins
    settings.cors_allow_origins = "https://app.example.com"
    try:
        with patches[0], patches[1], patches[2]:
            with (
                patch("app.routers.ws.ws_manager") as mock_mgr,
                patch("app.routers.ws.event_bridge") as mock_bridge,
                patch("app.routers.ws.get_task_event_cursor", new_callable=AsyncMock, return_value="7-0"),
            ):
                mock_mgr.connect = AsyncMock()
                mock_mgr.activate = MagicMock()
                mock_mgr.disconnect = MagicMock()
                mock_mgr.get_connections = MagicMock(return_value={"ws-1"})
                mock_mgr.run_heartbeat = AsyncMock()
                mock_bridge.ensure_started = AsyncMock()
                mock_bridge.stop = AsyncMock()
                with client.websocket_connect(
                    "/ws/task/00000000-0000-0000-0000-000000000001",
                    headers={
                        "origin": "https://same-origin.example.com",
                        "host": "same-origin.example.com",
                        **_AUTH_HEADERS,
                    },
                ) as ws:
                    data = ws.receive_json()
                    assert data["type"] == "connected"
    finally:
        settings.cors_allow_origins = original


def test_ws_accepts_authorization_header_token(client):
    """Bearer token in Authorization header is accepted without query token."""
    task = _mock_task()
    with (
        patch("app.routers.ws.get_session", _fake_session),
        patch(
            "app.routers.ws.get_task_exists",
            new_callable=AsyncMock,
            return_value=task,
        ),
        patch(
            "app.routers.ws._authenticate_ws_token",
            side_effect=lambda token: "user-1" if token == "header-token" else "",
        ),
        patch("app.routers.ws.get_task_event_cursor", new_callable=AsyncMock, return_value="7-0"),
        patch("app.routers.ws.ws_manager") as mock_mgr,
        patch("app.routers.ws.event_bridge") as mock_bridge,
    ):
        mock_mgr.connect = AsyncMock()
        mock_mgr.activate = MagicMock()
        mock_mgr.disconnect = MagicMock()
        mock_mgr.get_connections = MagicMock(return_value={"ws-1"})
        mock_mgr.run_heartbeat = AsyncMock()
        mock_bridge.ensure_started = AsyncMock()
        mock_bridge.stop = AsyncMock()
        with client.websocket_connect(
            "/ws/task/00000000-0000-0000-0000-000000000001",
            headers={"Authorization": "Bearer header-token"},
        ) as ws:
            data = ws.receive_json()
            assert data["type"] == "connected"


@pytest.mark.asyncio
async def test_ws_accepts_subprotocol_bearer_token_and_selects_auth_protocol():
    """Browser clients should authenticate through Sec-WebSocket-Protocol."""
    task_id = str(uuid.uuid4())
    task = _mock_task(task_id=task_id, owner_id="user-1")
    websocket = MagicMock()
    websocket.headers = {
        "sec-websocket-protocol": "agentic-nexus.auth, auth.aGVhZGVyLXRva2Vu",
    }
    websocket.accept = AsyncMock()
    websocket.send_text = AsyncMock()
    websocket.receive_text = AsyncMock(side_effect=WebSocketDisconnect(code=1000))
    websocket.close = AsyncMock()

    with (
        patch("app.routers.ws.get_session", _fake_session),
        patch("app.routers.ws.get_task_exists", new_callable=AsyncMock, return_value=task),
        patch(
            "app.routers.ws._authenticate_ws_token",
            side_effect=lambda token: "user-1" if token == "header-token" else "",
        ),
        patch("app.routers.ws.get_task_event_cursor", new_callable=AsyncMock, return_value="7-0"),
        patch("app.routers.ws.ws_manager") as mock_mgr,
        patch("app.routers.ws.event_bridge") as mock_bridge,
    ):
        mock_mgr.connect = AsyncMock()
        mock_mgr.activate = MagicMock()
        mock_mgr.disconnect = MagicMock()
        mock_mgr.get_connections = MagicMock(return_value=set())
        mock_mgr.run_heartbeat = AsyncMock()
        mock_bridge.ensure_started = AsyncMock()
        mock_bridge.stop = AsyncMock()

        await websocket_task(task_id, websocket, token="")

    websocket.accept.assert_awaited_once()
    assert websocket.accept.await_args.kwargs["subprotocol"] == "agentic-nexus.auth"


def test_ws_stops_bridge_when_last_connection_disconnects(client):
    """Last disconnect should stop the shared event bridge for this task."""
    patches = _auth_and_task_patches()
    with patches[0], patches[1], patches[2]:
        with (
            patch("app.routers.ws.ws_manager") as mock_mgr,
            patch("app.routers.ws.event_bridge") as mock_bridge,
            patch("app.routers.ws.get_task_event_cursor", new_callable=AsyncMock, return_value="7-0"),
        ):
            mock_mgr.connect = AsyncMock()
            mock_mgr.activate = MagicMock()
            mock_mgr.disconnect = MagicMock()
            mock_mgr.get_connections = MagicMock(return_value=set())
            mock_mgr.run_heartbeat = AsyncMock()
            mock_bridge.ensure_started = AsyncMock()
            mock_bridge.stop = AsyncMock()
            with client.websocket_connect(
                "/ws/task/00000000-0000-0000-0000-000000000001",
                headers=_AUTH_HEADERS,
            ) as ws:
                ws.receive_json()

            mock_bridge.stop.assert_awaited_once_with(
                "00000000-0000-0000-0000-000000000001"
            )


@pytest.mark.asyncio
async def test_ws_connected_event_sent_before_activation_for_active_bridge():
    """Existing bridges must not see the new socket before `connected` is sent."""
    task_id = str(uuid.uuid4())
    task = _mock_task(task_id=task_id, owner_id="user-1")
    websocket = MagicMock()
    websocket.headers = {"authorization": "Bearer test"}

    call_order: list[str] = []

    async def accept():
        call_order.append("accept")

    async def send_text(payload: str):
        call_order.append("connected")

    async def receive_text():
        raise WebSocketDisconnect(code=1000)

    async def close(*args, **kwargs):
        call_order.append("close")

    websocket.accept = AsyncMock(side_effect=accept)
    websocket.send_text = AsyncMock(side_effect=send_text)
    websocket.receive_text = AsyncMock(side_effect=receive_text)
    websocket.close = AsyncMock(side_effect=close)

    async def connect(task_id_arg: str, ws, *, ready: bool = True):
        call_order.append(f"connect:{ready}")

    async def ensure_started(task_id_arg: str, *, start_from_id: str = "$"):
        call_order.append("bridge")

    async def heartbeat(*args, **kwargs):
        await asyncio.sleep(3600)

    def activate(task_id_arg: str, ws):
        call_order.append("activate")

    with (
        patch("app.routers.ws.get_session", _fake_session),
        patch("app.routers.ws.get_task_exists", new_callable=AsyncMock, return_value=task),
        patch("app.routers.ws._authenticate_ws_token", return_value="user-1"),
        patch("app.routers.ws.get_task_event_cursor", new_callable=AsyncMock, return_value="11-0"),
        patch("app.routers.ws.ws_manager") as mock_mgr,
        patch("app.routers.ws.event_bridge") as mock_bridge,
    ):
        mock_mgr.connect = AsyncMock(side_effect=connect)
        mock_mgr.activate = MagicMock(side_effect=activate)
        mock_mgr.disconnect = MagicMock()
        mock_mgr.get_connections = MagicMock(return_value={"ws-1"})
        mock_mgr.run_heartbeat = AsyncMock(side_effect=heartbeat)
        mock_bridge.ensure_started = AsyncMock(return_value=False)
        mock_bridge.stop = AsyncMock()

        await websocket_task(task_id, websocket, token="test")

    assert call_order.index("connected") < call_order.index("activate")


@pytest.mark.asyncio
async def test_ws_closes_on_oversized_message():
    """Oversized client frames should close the connection instead of being ignored."""
    task_id = str(uuid.uuid4())
    task = _mock_task(task_id=task_id, owner_id="user-1")
    websocket = MagicMock()
    websocket.headers = {"authorization": "Bearer test"}

    async def receive_text():
        return "x" * (MAX_WS_MESSAGE_SIZE + 1)

    async def heartbeat(*args, **kwargs):
        await asyncio.sleep(3600)

    websocket.accept = AsyncMock()
    websocket.send_text = AsyncMock()
    websocket.receive_text = AsyncMock(side_effect=receive_text)
    websocket.close = AsyncMock()

    with (
        patch("app.routers.ws.get_session", _fake_session),
        patch("app.routers.ws.get_task_exists", new_callable=AsyncMock, return_value=task),
        patch("app.routers.ws._authenticate_ws_token", return_value="user-1"),
        patch("app.routers.ws.get_task_event_cursor", new_callable=AsyncMock, return_value="11-0"),
        patch("app.routers.ws.ws_manager") as mock_mgr,
        patch("app.routers.ws.event_bridge") as mock_bridge,
    ):
        mock_mgr.connect = AsyncMock()
        mock_mgr.activate = MagicMock()
        mock_mgr.disconnect = MagicMock()
        mock_mgr.get_connections = MagicMock(return_value=set())
        mock_mgr.record_pong = MagicMock()
        mock_mgr.run_heartbeat = AsyncMock(side_effect=heartbeat)
        mock_bridge.ensure_started = AsyncMock()
        mock_bridge.stop = AsyncMock()

        await websocket_task(task_id, websocket, token="test")

    websocket.close.assert_awaited_once_with(code=status.WS_1009_MESSAGE_TOO_BIG)
    mock_mgr.record_pong.assert_not_called()


@pytest.mark.asyncio
async def test_ws_replays_events_from_last_event_id_before_activation():
    task_id = str(uuid.uuid4())
    task = _mock_task(task_id=task_id, owner_id="user-1")
    websocket = MagicMock()
    websocket.headers = {"authorization": "Bearer test"}
    sent_payloads: list[dict] = []

    async def send_text(payload: str):
        sent_payloads.append(json.loads(payload))

    async def receive_text():
        raise WebSocketDisconnect(code=1000)

    websocket.accept = AsyncMock()
    websocket.send_text = AsyncMock(side_effect=send_text)
    websocket.receive_text = AsyncMock(side_effect=receive_text)
    websocket.close = AsyncMock()

    with (
        patch("app.routers.ws.get_session", _fake_session),
        patch("app.routers.ws.get_task_exists", new_callable=AsyncMock, return_value=task),
        patch("app.routers.ws._authenticate_ws_token", return_value="user-1"),
        patch("app.routers.ws.get_task_event_cursor", new_callable=AsyncMock, return_value="11-0"),
        patch("app.routers.ws.ws_manager") as mock_mgr,
        patch("app.routers.ws.event_bridge") as mock_bridge,
    ):
        mock_mgr.connect = AsyncMock()
        mock_mgr.activate = MagicMock()
        mock_mgr.disconnect = MagicMock()
        mock_mgr.get_connections = MagicMock(return_value=set())
        mock_mgr.run_heartbeat = AsyncMock()
        mock_bridge.replay_events = AsyncMock(
            return_value=[
                {
                    "type": "state_transition",
                    "task_id": task_id,
                    "event_id": "10-0",
                    "payload": {"from_state": "outline", "to_state": "writing"},
                }
            ]
        )
        mock_bridge.ensure_started = AsyncMock()
        mock_bridge.stop = AsyncMock()

        await websocket_task(task_id, websocket, token="test", last_event_id="9-0")

    assert sent_payloads[0]["type"] == "connected"
    assert sent_payloads[1]["type"] == "state_transition"
    mock_bridge.replay_events.assert_awaited_once_with(
        task_id,
        start_from_id="9-0",
        max_messages=200,
    )
    mock_bridge.ensure_started.assert_awaited_once_with(task_id, start_from_id="10-0")


@pytest.mark.asyncio
async def test_ws_replay_command_uses_last_acked_event_id():
    task_id = str(uuid.uuid4())
    task = _mock_task(task_id=task_id, owner_id="user-1")
    websocket = MagicMock()
    websocket.headers = {"authorization": "Bearer test"}

    incoming = iter(
        [
            json.dumps({"type": "ack", "event_id": "15-0"}),
            json.dumps({"type": "replay"}),
            WebSocketDisconnect(code=1000),
        ]
    )

    async def receive_text():
        item = next(incoming)
        if isinstance(item, Exception):
            raise item
        return item

    websocket.accept = AsyncMock()
    websocket.send_text = AsyncMock()
    websocket.receive_text = AsyncMock(side_effect=receive_text)
    websocket.close = AsyncMock()

    with (
        patch("app.routers.ws.get_session", _fake_session),
        patch("app.routers.ws.get_task_exists", new_callable=AsyncMock, return_value=task),
        patch("app.routers.ws._authenticate_ws_token", return_value="user-1"),
        patch("app.routers.ws.get_task_event_cursor", new_callable=AsyncMock, return_value="20-0"),
        patch("app.routers.ws.ws_manager") as mock_mgr,
        patch("app.routers.ws.event_bridge") as mock_bridge,
    ):
        mock_mgr.connect = AsyncMock()
        mock_mgr.activate = MagicMock()
        mock_mgr.disconnect = MagicMock()
        mock_mgr.get_connections = MagicMock(return_value=set())
        mock_mgr.run_heartbeat = AsyncMock()
        mock_bridge.replay_events = AsyncMock(return_value=[])
        mock_bridge.ensure_started = AsyncMock()
        mock_bridge.stop = AsyncMock()

        await websocket_task(task_id, websocket, token="test")

    mock_bridge.replay_events.assert_awaited_once_with(
        task_id,
        start_from_id="15-0",
        max_messages=200,
    )
