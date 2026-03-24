"""WebSocket 路由 — /ws/task/{task_id}"""

import asyncio
import base64
import json
import uuid as _uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.schemas.ws_event import ConnectedEvent
from app.models.task import Task
from app.security.auth import _parse_token_user_map, _parse_admin_users, _resolve_user_id_for_token
from app.services.event_bridge import event_bridge
from app.services.redis_streams import get_latest_stream_id, task_events_key
from app.services.ws_manager import ws_manager, ConnectionLimitError
from app.utils.logger import logger

router = APIRouter(tags=["websocket"])

MAX_WS_MESSAGE_SIZE = 1024  # 1 KB — pong messages are tiny


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


def _is_allowed_ws_origin(origin: str) -> bool:
    if not origin:
        return True
    allowed_origins = settings.cors_origins
    return "*" in allowed_origins or origin in allowed_origins


async def get_task_event_cursor(task_id: str) -> str:
    return await get_latest_stream_id(task_events_key(task_id))


@router.websocket("/ws/task/{task_id}")
async def websocket_task(
    task_id: str,
    websocket: WebSocket,
    token: str = Query(default=""),
):
    # --- Validate task_id format ---
    try:
        _uuid.UUID(task_id)
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # --- Origin validation (CSWSH protection) ---
    origin = websocket.headers.get("origin", "")
    if not _is_allowed_ws_origin(origin):
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
        await websocket.send_text(json.dumps(ConnectedEvent(task_id=task_id).model_dump()))
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
