"""业务层消息收发 — 基于 redis_streams.py 封装

职责：
  1. Agent 任务分配（发送到 agent inbox）
  2. Agent 结果上报（发送到 task events）
  3. 系统日志广播
  4. 消息持久化到 PostgreSQL messages 表
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.models.message import Message
from app.protocols.tea_protocol import (
    TeaEnvelope,
    build_tea_envelope,
    try_decode_tea_envelope,
)
from app.services.redis_streams import (
    MessageEnvelope,
    StreamMessage,
    SYSTEM_LOGS_KEY,
    agent_inbox_key,
    ensure_consumer_group,
    task_events_key,
    xack,
    xadd,
    xreadgroup,
)
from app.utils.logger import logger


# Consumer Group 名称约定
AGENT_INBOX_GROUP = "agent_workers"
TASK_EVENTS_GROUP = "task_subscribers"


RuntimeEnvelope = MessageEnvelope | TeaEnvelope


def _build_runtime_envelope(
    *,
    msg_type: str,
    from_agent: str = "",
    to_agent: str = "",
    task_id: str = "",
    node_id: str = "",
    payload: dict[str, Any] | None = None,
) -> RuntimeEnvelope:
    if settings.enable_tea_protocol:
        return build_tea_envelope(
            schema_version=settings.tea_protocol_version,
            msg_type=msg_type,
            from_agent=from_agent,
            to_agent=to_agent,
            task_id=task_id,
            node_id=node_id,
            payload=payload or {},
        )
    return MessageEnvelope(
        msg_type=msg_type,
        from_agent=from_agent,
        to_agent=to_agent,
        task_id=task_id,
        node_id=node_id,
        payload=payload or {},
    )


def decode_incoming_envelope(data: dict[str, Any]) -> RuntimeEnvelope:
    if settings.enable_tea_protocol:
        tea_envelope, error = try_decode_tea_envelope(
            data=data,
            supported_version=settings.tea_protocol_version,
        )
        if tea_envelope is not None:
            return tea_envelope
        if error:
            raise ValueError(f"TEA decode failed: {error}")
    return MessageEnvelope.from_redis(data)


# ---------------------------------------------------------------------------
# 发送 — 任务分配
# ---------------------------------------------------------------------------

async def send_task_assignment(
    *,
    agent_id: str | uuid.UUID,
    task_id: str | uuid.UUID,
    node_id: str | uuid.UUID,
    from_agent: str = "scheduler",
    payload: dict[str, Any] | None = None,
    persist: bool = True,
) -> str:
    """
    向 Agent Inbox 发送任务分配消息。

    Returns: Redis stream message-id
    """
    stream = agent_inbox_key(agent_id)
    await ensure_consumer_group(stream, AGENT_INBOX_GROUP)

    envelope = _build_runtime_envelope(
        msg_type="task_assign",
        from_agent=from_agent,
        to_agent=str(agent_id),
        task_id=str(task_id),
        node_id=str(node_id),
        payload=payload,
    )
    mid = await xadd(stream, envelope)

    if persist:
        await _persist_message(envelope)

    logger.bind(agent_id=str(agent_id), node_id=str(node_id)).info(
        "task_assign sent → {}", stream,
    )
    return mid


# ---------------------------------------------------------------------------
# 发送 — 结果上报
# ---------------------------------------------------------------------------

async def send_task_result(
    *,
    task_id: str | uuid.UUID,
    node_id: str | uuid.UUID,
    from_agent: str,
    result: dict[str, Any],
    persist: bool = True,
) -> str:
    """
    Agent 完成子任务后上报结果到 task events stream。

    Returns: Redis stream message-id
    """
    stream = task_events_key(task_id)

    envelope = _build_runtime_envelope(
        msg_type="task_result",
        from_agent=from_agent,
        task_id=str(task_id),
        node_id=str(node_id),
        payload=result,
    )
    mid = await xadd(stream, envelope)

    if persist:
        await _persist_message(envelope)

    logger.bind(task_id=str(task_id), node_id=str(node_id)).info(
        "task_result reported by {}", from_agent,
    )
    return mid


# ---------------------------------------------------------------------------
# 发送 — 通用 task event（WebSocket 转发用）
# ---------------------------------------------------------------------------

async def send_task_event(
    *,
    task_id: str | uuid.UUID,
    msg_type: str,
    payload: dict[str, Any],
    node_id: str | uuid.UUID = "",
    from_agent: str = "system",
) -> str:
    """发送通用任务事件到 task events stream。"""
    stream = task_events_key(task_id)

    envelope = _build_runtime_envelope(
        msg_type=msg_type,
        from_agent=from_agent,
        task_id=str(task_id),
        node_id=str(node_id),
        payload=payload,
    )
    return await xadd(stream, envelope)


# ---------------------------------------------------------------------------
# 发送 — 状态更新（WebSocket 转发用）
# ---------------------------------------------------------------------------

async def send_status_update(
    *,
    task_id: str | uuid.UUID,
    node_id: str | uuid.UUID = "",
    from_agent: str = "system",
    status: str,
    extra: dict[str, Any] | None = None,
) -> str:
    """
    发送 DAG 节点状态变更事件（供 WebSocket 订阅转发）。
    """
    payload: dict[str, Any] = {"status": status}
    if extra:
        payload.update(extra)

    return await send_task_event(
        task_id=task_id,
        node_id=node_id,
        from_agent=from_agent,
        msg_type="status_update",
        payload=payload,
    )


# ---------------------------------------------------------------------------
# 发送 — 系统日志
# ---------------------------------------------------------------------------

async def send_system_log(
    *,
    level: str = "info",
    message: str,
    task_id: str = "",
    agent_id: str = "",
    extra: dict[str, Any] | None = None,
) -> str:
    """广播系统日志到全局 Stream。"""
    payload: dict[str, Any] = {
        "level": level,
        "message": message,
    }
    if extra:
        payload.update(extra)

    envelope = _build_runtime_envelope(
        msg_type="log",
        from_agent=agent_id,
        task_id=task_id,
        payload=payload,
    )
    return await xadd(SYSTEM_LOGS_KEY, envelope)


# ---------------------------------------------------------------------------
# 接收 — Agent 消费 inbox
# ---------------------------------------------------------------------------

async def consume_agent_inbox(
    agent_id: str | uuid.UUID,
    consumer_name: str,
    *,
    count: int = 1,
    block: int = 2000,
) -> list[StreamMessage]:
    """
    Agent 从自己的 inbox 消费任务消息。

    consumer_name: 唯一标识此消费者实例（如 "writer_agent_1"）
    """
    stream = agent_inbox_key(agent_id)
    await ensure_consumer_group(stream, AGENT_INBOX_GROUP)

    new_messages = await xreadgroup(
        AGENT_INBOX_GROUP,
        consumer_name,
        {stream: ">"},
        count=count,
        block=block,
    )
    if new_messages:
        return new_messages

    # If no fresh assignment arrives, recover pending deliveries for this
    # consumer (e.g. after process/container restart).
    return await xreadgroup(
        AGENT_INBOX_GROUP,
        consumer_name,
        {stream: "0"},
        count=count,
        block=0,
    )


async def ack_agent_message(
    agent_id: str | uuid.UUID,
    message_id: str,
) -> int:
    """Agent 确认消息已处理。"""
    stream = agent_inbox_key(agent_id)
    return await xack(stream, AGENT_INBOX_GROUP, message_id)


# ---------------------------------------------------------------------------
# 接收 — 订阅 task events（WebSocket 后端用）
# ---------------------------------------------------------------------------

async def consume_task_events(
    task_id: str | uuid.UUID,
    consumer_name: str,
    *,
    count: int = 50,
    block: int = 1000,
) -> list[StreamMessage]:
    """
    WebSocket handler 消费任务事件流。
    """
    stream = task_events_key(task_id)
    await ensure_consumer_group(stream, TASK_EVENTS_GROUP)

    return await xreadgroup(
        TASK_EVENTS_GROUP,
        consumer_name,
        {stream: ">"},
        count=count,
        block=block,
    )


async def ack_task_event(
    task_id: str | uuid.UUID,
    message_id: str,
) -> int:
    """确认 task event 已处理。"""
    stream = task_events_key(task_id)
    return await xack(stream, TASK_EVENTS_GROUP, message_id)


# ---------------------------------------------------------------------------
# 消息持久化
# ---------------------------------------------------------------------------

async def _persist_message(envelope: RuntimeEnvelope) -> None:
    """将消息保存到 PostgreSQL messages 表。"""
    try:
        async with async_session_factory() as session:
            msg = Message(
                id=uuid.UUID(envelope.msg_id),
                task_id=uuid.UUID(envelope.task_id) if envelope.task_id else None,
                from_agent=envelope.from_agent or None,
                to_agent=envelope.to_agent or None,
                msg_type=envelope.msg_type,
                content=envelope.payload,
            )
            session.add(msg)
            await session.commit()
    except Exception as exc:
        # 唯一键冲突（重复消息）可安全忽略，其他错误上报
        from sqlalchemy.exc import IntegrityError
        if isinstance(exc, IntegrityError):
            logger.debug("duplicate message ignored: {}", envelope.msg_id)
        else:
            logger.opt(exception=True).error("failed to persist message {}", envelope.msg_id)


async def get_task_messages(
    task_id: str | uuid.UUID,
    *,
    msg_type: str | None = None,
    limit: int = 100,
) -> list[Message]:
    """查询任务的历史消息（从 PostgreSQL）。"""
    async with async_session_factory() as session:
        stmt = (
            select(Message)
            .where(Message.task_id == uuid.UUID(str(task_id)))
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        if msg_type:
            stmt = stmt.where(Message.msg_type == msg_type)
        result = await session.execute(stmt)
        return list(result.scalars().all())
