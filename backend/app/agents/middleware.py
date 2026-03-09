"""Agent 中间件管道 — 横切关注点处理

参考 DeerFlow 8层中间件链设计，通过可组合的中间件处理：
- 日志记录（任务开始/结束/耗时）
- Token用量追踪
- 任务超时控制
- 上下文摘要压缩
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from app.utils.logger import logger

if TYPE_CHECKING:
    from app.agents.base_agent import BaseAgent


class AgentMiddleware(ABC):
    """Agent 中间件抽象基类"""

    async def before_task(self, agent: BaseAgent, ctx: dict[str, Any]) -> dict[str, Any]:
        """任务处理前调用，可修改 context"""
        return ctx

    async def after_task(
        self, agent: BaseAgent, ctx: dict[str, Any], result: str,
    ) -> str:
        """任务处理后调用，可修改 result"""
        return result

    async def on_error(
        self, agent: BaseAgent, ctx: dict[str, Any], error: Exception,
    ) -> None:
        """任务出错时调用"""


class LoggingMiddleware(AgentMiddleware):
    """任务开始/结束/耗时/异常日志"""

    async def before_task(self, agent: BaseAgent, ctx: dict[str, Any]) -> dict[str, Any]:
        ctx["_start_time"] = time.monotonic()
        log = logger.bind(
            agent_id=str(agent.agent_id),
            agent_role=agent.role,
            task_id=ctx.get("task_id", ""),
            node_id=ctx.get("node_id", ""),
        )
        log.info("task started: {}", ctx.get("title", ""))
        return ctx

    async def after_task(
        self, agent: BaseAgent, ctx: dict[str, Any], result: str,
    ) -> str:
        elapsed = time.monotonic() - ctx.get("_start_time", time.monotonic())
        log = logger.bind(
            agent_id=str(agent.agent_id),
            agent_role=agent.role,
            task_id=ctx.get("task_id", ""),
            node_id=ctx.get("node_id", ""),
            elapsed_s=round(elapsed, 2),
        )
        log.info("task completed ({:.2f}s)", elapsed)
        return result

    async def on_error(
        self, agent: BaseAgent, ctx: dict[str, Any], error: Exception,
    ) -> None:
        elapsed = time.monotonic() - ctx.get("_start_time", time.monotonic())
        log = logger.bind(
            agent_id=str(agent.agent_id),
            agent_role=agent.role,
            task_id=ctx.get("task_id", ""),
            node_id=ctx.get("node_id", ""),
            elapsed_s=round(elapsed, 2),
        )
        log.opt(exception=True).error("task failed ({:.2f}s): {}", elapsed, error)


class TokenTrackingMiddleware(AgentMiddleware):
    """记录 LLM token 用量到 TokenTracker"""

    async def after_task(
        self, agent: BaseAgent, ctx: dict[str, Any], result: str,
    ) -> str:
        if agent.token_tracker:
            usage = ctx.get("_token_usage")
            if usage:
                agent.token_tracker.record(
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    cached_tokens=usage.get("cached_tokens", 0),
                    task_id=ctx.get("task_id"),
                    role=agent.role,
                )
        return result


class TimeoutMiddleware(AgentMiddleware):
    """任务超时自动取消 — 通过 asyncio.timeout 实现"""

    def __init__(self, timeout_seconds: float = 120.0) -> None:
        self._timeout = timeout_seconds

    async def before_task(self, agent: BaseAgent, ctx: dict[str, Any]) -> dict[str, Any]:
        ctx["_timeout_seconds"] = self._timeout
        return ctx


class ContextSummaryMiddleware(AgentMiddleware):
    """长上下文自动摘要压缩 — 超过窗口 75% 时压缩"""

    MAX_CONTEXT_CHARS = 30000  # 约 7500 tokens 的粗略近似

    async def before_task(self, agent: BaseAgent, ctx: dict[str, Any]) -> dict[str, Any]:
        messages = ctx.get("messages", [])
        if not messages:
            return ctx

        total_len = sum(len(m.get("content", "")) for m in messages)
        if total_len <= self.MAX_CONTEXT_CHARS:
            return ctx

        # 压缩：保留 system + 最新 2 条，中间部分请求 LLM 摘要
        if len(messages) <= 3 or not agent.llm_client:
            return ctx

        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        if len(non_system) <= 2:
            return ctx

        to_summarize = non_system[:-2]
        recent = non_system[-2:]

        summary_text = "\n".join(
            f"[{m.get('role', 'unknown')}]: {m.get('content', '')[:200]}"
            for m in to_summarize
        )

        try:
            compressed = await agent.llm_client.chat(
                messages=[{
                    "role": "user",
                    "content": f"请将以下对话历史压缩为简短摘要，保留关键信息：\n\n{summary_text}",
                }],
                role="manager",
                max_tokens=500,
            )
            ctx = {
                **ctx,
                "messages": system_msgs + [
                    {"role": "user", "content": f"[历史摘要]: {compressed}"},
                    *recent,
                ],
            }
            logger.bind(
                agent_id=str(agent.agent_id),
                original_len=total_len,
            ).debug("context compressed")
        except Exception:
            logger.opt(exception=True).warning("context compression failed, using original")

        return ctx


# 默认中间件栈（执行顺序：Logging → TokenTracking → Timeout → ContextSummary → Agent.handle_task）
DEFAULT_MIDDLEWARES: tuple[AgentMiddleware, ...] = (
    LoggingMiddleware(),
    TokenTrackingMiddleware(),
    TimeoutMiddleware(),
    ContextSummaryMiddleware(),
)
