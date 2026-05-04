"""WebSocket 路由 — /ws/task/{task_id}"""

import asyncio
import base64
import json
import re
import uuid as _uuid
from urllib.parse import urlparse

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.schemas.ws_event import ConnectedEvent
from app.models.task import Task
from app.security.auth import _parse_token_user_map, _parse_admin_users, _resolve_user_id_for_token
from app.services.event_bridge import HIGH_PRIORITY_EVENT_TYPES, event_bridge
from app.services.redis_streams import get_latest_stream_id, task_events_key
from app.services.ws_manager import ws_manager, ConnectionLimitError
from app.utils.logger import logger

router = APIRouter(tags=["websocket"])

MAX_WS_MESSAGE_SIZE = 1024  # 1 KB — pong messages are tiny
MONITOR_CONTRACT_VERSION = "stage-observability-v1"
STREAM_ID_PATTERN = re.compile(r"^\d+-\d+$")
REPLAY_BATCH_SIZE = 200
REPLAY_MAX_EVENTS = 5000


async def get_task_exists(task_id: str, session: AsyncSession) -> Task | None:
    return await session.get(Task, task_id)


def _authenticate_ws_token(token: str) -> str:
    """Validate bearer token, return user_id or empty string."""
    token_map = _parse_token_user_map(settings.task_auth_tokens)
    return _resolve_user_id_for_token(token, token_map)


def _extract_bearer_token(value: str) -> str:
    raw = (value or "").strip()
    if not raw.lower().startswith("bearer "):
        return ""
    return raw[7:].strip()


def _decode_base64url_token(encoded: str) -> str:
    candidate = (encoded or "").strip()
    if not candidate:
        return ""
    padding = "=" * (-len(candidate) % 4)
    try:
        decoded = base64.urlsafe_b64decode(candidate + padding)
        return decoded.decode("utf-8")
    except Exception:
        return ""


def _extract_subprotocol_token(websocket: WebSocket) -> tuple[str, str | None]:
    raw = websocket.headers.get("sec-websocket-protocol", "")
    protocols = [item.strip() for item in raw.split(",") if item.strip()]
    if len(protocols) < 2 or protocols[0] != "agentic-nexus.auth":
        return "", None

    auth_protocol = protocols[1]
    if not auth_protocol.startswith("auth."):
        return "", None

    token = _decode_base64url_token(auth_protocol[5:])
    if not token:
        return "", None

    return token, "agentic-nexus.auth"


def _resolve_ws_token(websocket: WebSocket, query_token: str) -> tuple[str, str | None]:
    header_token = _extract_bearer_token(
        websocket.headers.get("authorization", "")
    )
    if header_token:
        return header_token, None

    protocol_token, selected_subprotocol = _extract_subprotocol_token(websocket)
    if protocol_token:
        return protocol_token, selected_subprotocol

    if settings.ws_allow_query_token_fallback:
        return (query_token or "").strip(), None
    return "", None


def _is_allowed_ws_origin(origin: str, host: str) -> bool:
    if not origin:
        return True
    allowed_origins = settings.cors_origins
    if "*" in allowed_origins or origin in allowed_origins:
        return True

    # Allow same-origin WS handshakes so local direct mode and tunnels work
    # without requiring dynamic domains in static CORS allow-lists.
    try:
        origin_host = urlparse(origin).netloc.strip().lower()
    except Exception:
        origin_host = ""
    request_host = (host or "").strip().lower()
    return bool(origin_host and request_host and origin_host == request_host)


def _is_valid_stream_id(value: str) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    if raw == "$":
        return True
    return bool(STREAM_ID_PATTERN.match(raw))


async def get_task_event_cursor(task_id: str) -> str:
    return await get_latest_stream_id(task_events_key(task_id))


async def _replay_from_cursor(task_id: str, websocket: WebSocket, start_cursor: str) -> str:
    cursor = str(start_cursor or "").strip()
    if not _is_valid_stream_id(cursor):
        return cursor

    replayed = 0
    while replayed < REPLAY_MAX_EVENTS:
        batch = min(REPLAY_BATCH_SIZE, REPLAY_MAX_EVENTS - replayed)
        replay_events = await event_bridge.replay_events(
            task_id,
            start_from_id=cursor,
            max_messages=batch,
        )
        if not replay_events:
            break
        for replay_event in replay_events:
            await websocket.send_text(json.dumps(replay_event, ensure_ascii=False))
        replayed += len(replay_events)
        last_event_id = str(replay_events[-1].get("event_id") or "").strip()
        if _is_valid_stream_id(last_event_id):
            cursor = last_event_id
        if len(replay_events) < batch:
            break
    return cursor


@router.websocket("/ws/task/{task_id}")
async def websocket_task(
    task_id: str,
    websocket: WebSocket,
    token: str = Query(default=""),
    last_event_id: str = Query(default=""),
):
    # --- Validate task_id format ---
    try:
        _uuid.UUID(task_id)
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # --- Origin validation (CSWSH protection) ---
    origin = websocket.headers.get("origin", "")
    host = websocket.headers.get("host", "")
    if not _is_allowed_ws_origin(origin, host):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # --- Authenticate via Authorization header first, then query fallback ---
    resolved_token, accepted_subprotocol = _resolve_ws_token(websocket, token)
    user_id = _authenticate_ws_token(resolved_token)
    if not user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # --- Verify task exists and user has access ---
    task = None
    async for session in get_session():
        task = await get_task_exists(task_id, session)
        break
    if task is None:
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        except Exception:
            pass
        return

    admin_users = _parse_admin_users(settings.admin_user_ids)
    if not task.owner_id and user_id not in admin_users:
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        except Exception:
            pass
        return
    if task.owner_id != user_id and user_id not in admin_users:
        try:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        except Exception:
            pass
        return

    # --- Accept and manage connection ---
    heartbeat_task: asyncio.Task[None] | None = None
    if accepted_subprotocol:
        await websocket.accept(subprotocol=accepted_subprotocol)
    else:
        await websocket.accept()
    try:
        await ws_manager.connect(task_id, websocket, ready=False)
    except ConnectionLimitError:
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return

    last_acked_event_id = str(last_event_id or "").strip() if _is_valid_stream_id(last_event_id) else ""
    try:
        try:
            start_from_id = await get_task_event_cursor(task_id)
        except Exception:
            logger.bind(task_id=task_id).opt(exception=True).warning(
                "Failed to load task event cursor, falling back to latest-only bridge"
            )
            start_from_id = "$"

        log = logger.bind(task_id=task_id, user_id=user_id)
        log.info("WS client connected")
        await websocket.send_text(
            json.dumps(
                ConnectedEvent(
                    task_id=task_id,
                    payload={
                        "monitor_contract_version": MONITOR_CONTRACT_VERSION,
                        "start_from_id": start_from_id,
                        "replay_from_id": last_acked_event_id or None,
                        "ack_required_types": sorted(HIGH_PRIORITY_EVENT_TYPES),
                    },
                ).model_dump()
            )
        )
        if last_acked_event_id:
            start_from_id = await _replay_from_cursor(
                task_id,
                websocket,
                last_acked_event_id,
            )
        ws_manager.activate(task_id, websocket)
        await event_bridge.ensure_started(task_id, start_from_id=start_from_id)
        heartbeat_task = asyncio.create_task(
            ws_manager.run_heartbeat(websocket, task_id)
        )
        while True:
            raw = await websocket.receive_text()
            if len(raw) > MAX_WS_MESSAGE_SIZE:
                log.warning("WS message too large ({} bytes), closing", len(raw))
                await websocket.close(code=status.WS_1009_MESSAGE_TOO_BIG)
                break
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "pong":
                ws_manager.record_pong(websocket)
                continue
            if msg.get("type") == "ack":
                event_id = str(msg.get("event_id") or "").strip()
                if _is_valid_stream_id(event_id):
                    last_acked_event_id = event_id
                continue
            if msg.get("type") == "replay":
                replay_cursor = str(msg.get("last_event_id") or "").strip() or last_acked_event_id
                if not _is_valid_stream_id(replay_cursor):
                    continue
                await _replay_from_cursor(
                    task_id,
                    websocket,
                    replay_cursor,
                )
    except WebSocketDisconnect:
        log.info("WS client disconnected")
    finally:
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
        ws_manager.disconnect(task_id, websocket)
        if not ws_manager.get_connections(task_id):
            await event_bridge.stop(task_id)
