"""任务超时监控 — 基于 Redis Sorted Set 轮询

工作原理：
  1. 调度器分配节点时调用 watch_node() 注册超时
  2. 后台协程 run_timeout_monitor() 周期扫描已超时节点
  3. 超时后回调 on_timeout 处理（重试 / 标记失败 / 转移）
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Awaitable, Callable

from app.services.redis_streams import (
    add_timeout_watch,
    get_timed_out_nodes,
    remove_timeout_watch,
)
from app.utils.logger import logger

# 默认节点执行超时（秒）
DEFAULT_NODE_TIMEOUT_SECONDS = 300  # 5 分钟


async def watch_node(
    node_id: str | uuid.UUID,
    *,
    timeout_seconds: float = DEFAULT_NODE_TIMEOUT_SECONDS,
) -> None:
    """为节点注册超时监控。"""
    deadline = time.time() + timeout_seconds
    await add_timeout_watch(str(node_id), deadline)
    logger.bind(node_id=str(node_id)).debug(
        "timeout watch registered, {}s", timeout_seconds,
    )


async def unwatch_node(node_id: str | uuid.UUID) -> None:
    """节点完成时取消超时监控。"""
    await remove_timeout_watch(str(node_id))


# Type for timeout callback
TimeoutCallback = Callable[[str], Awaitable[None]]


async def run_timeout_monitor(
    on_timeout: TimeoutCallback,
    *,
    poll_interval: float = 5.0,
    stop_event: asyncio.Event | None = None,
) -> None:
    """
    后台轮询协程 — 扫描已超时节点并触发回调。

    on_timeout(node_id): 由调度器提供的回调，处理超时逻辑
    stop_event: 设置后优雅退出循环
    """
    _stop = stop_event or asyncio.Event()
    logger.info("timeout monitor started, poll_interval={}s", poll_interval)

    while not _stop.is_set():
        try:
            timed_out = await get_timed_out_nodes()
            for node_id in timed_out:
                logger.bind(node_id=node_id).warning("node timed out")
                await remove_timeout_watch(node_id)
                try:
                    await on_timeout(node_id)
                except Exception:
                    logger.opt(exception=True).error(
                        "timeout callback failed for node {}", node_id,
                    )
        except Exception:
            logger.opt(exception=True).error("timeout monitor scan error")

        # 等待 poll_interval 或 stop 信号
        try:
            await asyncio.wait_for(_stop.wait(), timeout=poll_interval)
            break  # stop event was set
        except asyncio.TimeoutError:
            pass  # normal polling cycle

    logger.info("timeout monitor stopped")
