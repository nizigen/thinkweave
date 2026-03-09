"""Redis Streams 封装 — XADD / XREADGROUP / XACK / Consumer Group 管理

通道命名规范（来自 BACKEND_STRUCTURE.md）：
  agent:{agent_id}:inbox     – Agent 任务接收流（Consumer Group 模式）
  task:{task_id}:events      – 任务事件流（WebSocket 转发）
  system:logs                – 全局日志流

辅助数据结构：
  scheduler:timeout_watch    – Sorted Set，score = deadline_timestamp
  agent:{agent_id}:state     – Hash，Agent 运行时状态
  task:{task_id}:dag_state   – Hash，DAG 节点状态快照
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import redis.asyncio as aioredis

from app.redis_client import redis_client
from app.utils.logger import logger


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StreamMessage:
    """从 Redis Stream 读取到的单条消息。"""

    stream: str
    message_id: str
    data: dict[str, Any]


@dataclass(frozen=True)
class MessageEnvelope:
    """业务消息信封 — 写入 Stream 前序列化，读出后反序列化。"""

    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    msg_type: str = ""
    from_agent: str = ""
    to_agent: str = ""
    task_id: str = ""
    node_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    ttl: int = 60  # seconds — 预留字段，当前未做消费端过期检查

    def to_redis(self) -> dict[str, str]:
        """序列化为 Redis Stream field-value 映射（全部字符串）。"""
        return {
            "msg_id": self.msg_id,
            "msg_type": self.msg_type,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "task_id": self.task_id,
            "node_id": self.node_id,
            "payload": json.dumps(self.payload, ensure_ascii=False),
            "timestamp": str(self.timestamp),
            "ttl": str(self.ttl),
        }

    @classmethod
    def from_redis(cls, data: dict[str, str]) -> MessageEnvelope:
        """从 Redis Stream 读出的 field-value 映射反序列化。"""
        return cls(
            msg_id=data.get("msg_id", ""),
            msg_type=data.get("msg_type", ""),
            from_agent=data.get("from_agent", ""),
            to_agent=data.get("to_agent", ""),
            task_id=data.get("task_id", ""),
            node_id=data.get("node_id", ""),
            payload=json.loads(data.get("payload", "{}")),
            timestamp=float(data.get("timestamp", "0")),
            ttl=int(data.get("ttl", "60")),
        )


# ---------------------------------------------------------------------------
# Stream key builders
# ---------------------------------------------------------------------------

def agent_inbox_key(agent_id: str | uuid.UUID) -> str:
    return f"agent:{agent_id}:inbox"


def task_events_key(task_id: str | uuid.UUID) -> str:
    return f"task:{task_id}:events"


def agent_state_key(agent_id: str | uuid.UUID) -> str:
    return f"agent:{agent_id}:state"


def task_dag_state_key(task_id: str | uuid.UUID) -> str:
    return f"task:{task_id}:dag_state"


SYSTEM_LOGS_KEY = "system:logs"
TIMEOUT_WATCH_KEY = "scheduler:timeout_watch"
READY_NODES_KEY = "scheduler:ready_nodes"


# ---------------------------------------------------------------------------
# Consumer Group 管理
# ---------------------------------------------------------------------------

async def ensure_consumer_group(
    stream: str,
    group: str,
    *,
    r: aioredis.Redis | None = None,
) -> None:
    """确保 Consumer Group 存在；如果 Stream 不存在则自动创建。"""
    cli = r or redis_client
    try:
        await cli.xgroup_create(stream, group, id="0", mkstream=True)
    except aioredis.ResponseError as exc:
        # BUSYGROUP = group already exists → safe to ignore
        if "BUSYGROUP" not in str(exc):
            raise


# ---------------------------------------------------------------------------
# 核心 Stream 操作
# ---------------------------------------------------------------------------

async def xadd(
    stream: str,
    envelope: MessageEnvelope,
    *,
    maxlen: int | None = 10000,
    r: aioredis.Redis | None = None,
) -> str:
    """向 Stream 追加消息，返回 message-id。"""
    cli = r or redis_client
    mid = await cli.xadd(stream, envelope.to_redis(), maxlen=maxlen, approximate=True)
    logger.bind(stream=stream, msg_type=envelope.msg_type).debug(
        "XADD → {}", mid,
    )
    return mid


async def xreadgroup(
    group: str,
    consumer: str,
    streams: dict[str, str],
    *,
    count: int = 10,
    block: int = 2000,
    r: aioredis.Redis | None = None,
) -> list[StreamMessage]:
    """
    Consumer Group 消费：阻塞读取未确认消息。

    streams: {stream_key: ">"}  — ">" 表示只读取新消息
    block:   阻塞毫秒数，0=不阻塞
    """
    cli = r or redis_client
    raw = await cli.xreadgroup(
        group, consumer, streams=streams, count=count, block=block,
    )
    if not raw:
        return []

    messages: list[StreamMessage] = []
    for stream_key, entries in raw:
        for mid, fields in entries:
            messages.append(StreamMessage(stream=stream_key, message_id=mid, data=fields))
    return messages


async def xack(
    stream: str,
    group: str,
    *message_ids: str,
    r: aioredis.Redis | None = None,
) -> int:
    """确认消息已处理。"""
    cli = r or redis_client
    return await cli.xack(stream, group, *message_ids)


async def xread_latest(
    streams: dict[str, str],
    *,
    count: int = 50,
    block: int = 5000,
    r: aioredis.Redis | None = None,
) -> list[StreamMessage]:
    """非 Consumer Group 读取 — 用于 WebSocket 订阅等只读场景。

    block: 阻塞等待毫秒数。默认 5000ms，调用者应在外层循环中重复调用。
           传 0 表示非阻塞立即返回。不建议传极大值以免协程无法取消。
    """
    cli = r or redis_client
    raw = await cli.xread(streams=streams, count=count, block=block)
    if not raw:
        return []

    messages: list[StreamMessage] = []
    for stream_key, entries in raw:
        for mid, fields in entries:
            messages.append(StreamMessage(stream=stream_key, message_id=mid, data=fields))
    return messages


# ---------------------------------------------------------------------------
# Sorted Set — 超时监控
# ---------------------------------------------------------------------------

async def add_timeout_watch(
    node_id: str,
    deadline: float,
    *,
    r: aioredis.Redis | None = None,
) -> None:
    """将 node_id 加入超时监控 Sorted Set（score = deadline_timestamp）。"""
    cli = r or redis_client
    await cli.zadd(TIMEOUT_WATCH_KEY, {node_id: deadline})
    logger.bind(node_id=node_id).debug("timeout watch set, deadline={}", deadline)


async def remove_timeout_watch(
    node_id: str,
    *,
    r: aioredis.Redis | None = None,
) -> None:
    """移除超时监控。"""
    cli = r or redis_client
    await cli.zrem(TIMEOUT_WATCH_KEY, node_id)


async def get_timed_out_nodes(
    *,
    r: aioredis.Redis | None = None,
) -> list[str]:
    """获取所有已超时的 node_id（deadline <= now）。"""
    cli = r or redis_client
    now = time.time()
    return await cli.zrangebyscore(TIMEOUT_WATCH_KEY, "-inf", now)


# ---------------------------------------------------------------------------
# Sorted Set — 就绪节点队列
# ---------------------------------------------------------------------------

async def push_ready_node(
    node_id: str,
    priority: float = 0.0,
    *,
    r: aioredis.Redis | None = None,
) -> None:
    """将就绪节点加入优先队列（score = priority，越小越优先）。"""
    cli = r or redis_client
    await cli.zadd(READY_NODES_KEY, {node_id: priority})


async def pop_ready_nodes(
    count: int = 10,
    *,
    r: aioredis.Redis | None = None,
) -> list[str]:
    """弹出最高优先级的就绪节点（原子操作）。"""
    cli = r or redis_client
    # ZPOPMIN 返回 [(member, score), ...]
    results = await cli.zpopmin(READY_NODES_KEY, count=count)
    return [member for member, _score in results]


# ---------------------------------------------------------------------------
# Hash — Agent 状态
# ---------------------------------------------------------------------------

async def set_agent_state(
    agent_id: str | uuid.UUID,
    state: dict[str, str],
    *,
    r: aioredis.Redis | None = None,
) -> None:
    """更新 Agent 运行时状态（Hash 多字段写入）。"""
    cli = r or redis_client
    key = agent_state_key(agent_id)
    await cli.hset(key, mapping=state)


async def get_agent_state(
    agent_id: str | uuid.UUID,
    *,
    r: aioredis.Redis | None = None,
) -> dict[str, str]:
    """读取 Agent 完整运行时状态。"""
    cli = r or redis_client
    key = agent_state_key(agent_id)
    return await cli.hgetall(key)


async def delete_agent_state(
    agent_id: str | uuid.UUID,
    *,
    r: aioredis.Redis | None = None,
) -> None:
    """清理 Agent 状态（Agent 下线时调用）。"""
    cli = r or redis_client
    await cli.delete(agent_state_key(agent_id))


# ---------------------------------------------------------------------------
# Hash — DAG 节点状态快照
# ---------------------------------------------------------------------------

async def set_dag_node_status(
    task_id: str | uuid.UUID,
    node_id: str,
    status: str,
    *,
    r: aioredis.Redis | None = None,
) -> None:
    """更新 DAG 某节点的状态快照。"""
    cli = r or redis_client
    key = task_dag_state_key(task_id)
    await cli.hset(key, node_id, status)


async def get_dag_state(
    task_id: str | uuid.UUID,
    *,
    r: aioredis.Redis | None = None,
) -> dict[str, str]:
    """获取整个 DAG 的节点状态快照 {node_id: status}。"""
    cli = r or redis_client
    return await cli.hgetall(task_dag_state_key(task_id))


async def delete_dag_state(
    task_id: str | uuid.UUID,
    *,
    r: aioredis.Redis | None = None,
) -> None:
    """任务完成后清理 DAG 状态快照。"""
    cli = r or redis_client
    await cli.delete(task_dag_state_key(task_id))
