"""Agent 心跳管理 — 发送 / 检测 / 超时处理

每个 Agent 定期调用 send_heartbeat()，后台协程 monitor_heartbeats()
扫描过期 Agent 并标记为 offline。
"""

from __future__ import annotations

import time
import uuid

from app.services.redis_streams import (
    agent_state_key,
    get_agent_state,
    set_agent_state,
)
from app.redis_client import redis_client  # noqa: F401 — used in pipeline ops
from app.utils.logger import logger

# 心跳超时阈值（秒）— Agent 超过此时间未发心跳视为离线
HEARTBEAT_TIMEOUT_SECONDS = 30


async def send_heartbeat(
    agent_id: str | uuid.UUID,
    *,
    status: str = "idle",
    current_task: str = "",
    current_node: str = "",
) -> None:
    """Agent 发送心跳 — 更新 Redis Hash 中的状态和时间戳。"""
    now = str(time.time())
    state = {
        "status": status,
        "current_task": current_task,
        "current_node": current_node,
        "last_heartbeat": now,
    }
    await set_agent_state(agent_id, state)
    logger.bind(agent_id=str(agent_id)).debug("heartbeat sent, status={}", status)


async def check_agent_alive(
    agent_id: str | uuid.UUID,
) -> bool:
    """检查单个 Agent 是否在线（心跳未超时）。"""
    state = await get_agent_state(agent_id)
    if not state:
        return False

    last_hb = float(state.get("last_heartbeat", "0"))
    return (time.time() - last_hb) < HEARTBEAT_TIMEOUT_SECONDS


async def get_all_agent_states(
    agent_ids: list[str | uuid.UUID],
) -> dict[str, dict[str, str]]:
    """批量获取多个 Agent 的运行时状态（pipeline 批量化）。"""
    if not agent_ids:
        return {}

    result: dict[str, dict[str, str]] = {}
    pipe = redis_client.pipeline(transaction=False)
    keys = [agent_state_key(aid) for aid in agent_ids]
    for key in keys:
        pipe.hgetall(key)
    states = await pipe.execute()

    for aid, state in zip(agent_ids, states):
        if state:
            result[str(aid)] = state
    return result


async def find_expired_agents(
    agent_ids: list[str | uuid.UUID],
) -> list[str]:
    """返回所有心跳超时的 agent_id 列表（pipeline 批量化）。"""
    if not agent_ids:
        return []

    expired: list[str] = []
    now = time.time()

    pipe = redis_client.pipeline(transaction=False)
    keys = [agent_state_key(aid) for aid in agent_ids]
    for key in keys:
        pipe.hgetall(key)
    states = await pipe.execute()

    for aid, state in zip(agent_ids, states):
        if not state:
            expired.append(str(aid))
            continue
        last_hb = float(state.get("last_heartbeat", "0"))
        if (now - last_hb) >= HEARTBEAT_TIMEOUT_SECONDS:
            expired.append(str(aid))
    return expired
