"""Composable agent middleware for runtime cross-cutting concerns."""

from __future__ import annotations

import time
from abc import ABC
from collections import OrderedDict
from typing import TYPE_CHECKING, Any

from app.memory.session import SessionMemory
from app.services import communicator
from app.utils.logger import logger

if TYPE_CHECKING:
    from app.agents.base_agent import BaseAgent


class AgentMiddleware(ABC):
    """Base class for agent middleware hooks."""

    async def before_task(self, agent: BaseAgent, ctx: dict[str, Any]) -> dict[str, Any]:
        return ctx

    async def after_task(self, agent: BaseAgent, ctx: dict[str, Any], result: str) -> str:
        return result

    async def on_error(self, agent: BaseAgent, ctx: dict[str, Any], error: Exception) -> None:
        return None


class LoggingMiddleware(AgentMiddleware):
    """Track task start, finish, duration, and failure logging."""

    async def _emit_node_event(
        self,
        agent: BaseAgent,
        ctx: dict[str, Any],
        *,
        status: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        task_id = str(ctx.get("task_id", "")).strip()
        node_id = str(ctx.get("node_id", "")).strip()
        if not task_id:
            return

        payload: dict[str, Any] = {
            "status": status,
            "title": ctx.get("title", ""),
            "agent_role": agent.role,
            "agent_id": str(agent.agent_id),
        }
        if extra:
            payload.update(extra)

        try:
            await communicator.send_task_event(
                task_id=task_id,
                node_id=node_id,
                from_agent=str(agent.agent_id),
                msg_type="node_update",
                payload=payload,
            )
        except Exception:
            logger.opt(exception=True).warning("failed to emit node_update event")

    async def before_task(self, agent: BaseAgent, ctx: dict[str, Any]) -> dict[str, Any]:
        current_ctx = {**ctx, "_start_time": time.monotonic()}
        log = logger.bind(
            agent_id=str(agent.agent_id),
            agent_role=agent.role,
            task_id=current_ctx.get("task_id", ""),
            node_id=current_ctx.get("node_id", ""),
        )
        log.info("task started: {}", current_ctx.get("title", ""))
        await self._emit_node_event(agent, current_ctx, status="running")
        return current_ctx

    async def after_task(self, agent: BaseAgent, ctx: dict[str, Any], result: str) -> str:
        elapsed = time.monotonic() - ctx.get("_start_time", time.monotonic())
        log = logger.bind(
            agent_id=str(agent.agent_id),
            agent_role=agent.role,
            task_id=ctx.get("task_id", ""),
            node_id=ctx.get("node_id", ""),
            elapsed_s=round(elapsed, 2),
        )
        log.info("task completed ({:.2f}s)", elapsed)
        await self._emit_node_event(
            agent,
            ctx,
            status="completed",
            extra={"elapsed_s": round(elapsed, 2)},
        )
        return result

    async def on_error(self, agent: BaseAgent, ctx: dict[str, Any], error: Exception) -> None:
        elapsed = time.monotonic() - ctx.get("_start_time", time.monotonic())
        log = logger.bind(
            agent_id=str(agent.agent_id),
            agent_role=agent.role,
            task_id=ctx.get("task_id", ""),
            node_id=ctx.get("node_id", ""),
            elapsed_s=round(elapsed, 2),
        )
        log.opt(exception=True).error("task failed ({:.2f}s): {}", elapsed, error)
        await self._emit_node_event(
            agent,
            ctx,
            status="failed",
            extra={
                "elapsed_s": round(elapsed, 2),
                "error_code": "agent_execution_failed",
                "error_message": "Task execution failed",
            },
        )


class TokenTrackingMiddleware(AgentMiddleware):
    """Write token usage into the task token tracker when available."""

    async def after_task(self, agent: BaseAgent, ctx: dict[str, Any], result: str) -> str:
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
    """Attach task timeout metadata for BaseAgent.process_task."""

    def __init__(self, timeout_seconds: float = 300.0) -> None:
        self._timeout = timeout_seconds

    async def before_task(self, agent: BaseAgent, ctx: dict[str, Any]) -> dict[str, Any]:
        return {**ctx, "_timeout_seconds": self._timeout}


class ContextSummaryMiddleware(AgentMiddleware):
    """Compress oversized message history before task execution."""

    DEFAULT_MAX_CHARS = 30000
    CHARS_PER_TOKEN = 4
    THRESHOLD_RATIO = 0.75

    async def before_task(self, agent: BaseAgent, ctx: dict[str, Any]) -> dict[str, Any]:
        messages = ctx.get("messages", [])
        if not messages:
            return ctx

        max_chars = self.DEFAULT_MAX_CHARS
        if hasattr(agent.llm_client, "get_model_config"):
            try:
                config = agent.llm_client.get_model_config(agent.role)
                context_window = getattr(config, "context_window", 0)
                if context_window > 0:
                    max_chars = int(
                        context_window * self.CHARS_PER_TOKEN * self.THRESHOLD_RATIO
                    )
            except Exception:
                pass

        total_len = sum(len(message.get("content", "")) for message in messages)
        if total_len <= max_chars:
            return ctx

        if len(messages) <= 3 or not agent.llm_client:
            return ctx

        system_msgs = [message for message in messages if message.get("role") == "system"]
        non_system = [message for message in messages if message.get("role") != "system"]
        if len(non_system) <= 2:
            return ctx

        to_summarize = non_system[:-2]
        recent = non_system[-2:]
        summary_text = "\n".join(
            f"[{message.get('role', 'unknown')}]: {message.get('content', '')[:200]}"
            for message in to_summarize
        )

        try:
            compressed = await agent.llm_client.chat(
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Please compress the following conversation history into a short "
                            f"summary while preserving the key facts:\n\n{summary_text}"
                        ),
                    }
                ],
                role="manager",
                max_tokens=500,
            )
            return {
                **ctx,
                "messages": system_msgs
                + [{"role": "user", "content": f"[history summary]: {compressed}"}, *recent],
            }
        except Exception:
            logger.opt(exception=True).warning("context compression failed, using original")
            return ctx


class MemoryMiddleware(AgentMiddleware):
    """Role-aware session memory injection and persistence."""

    def __init__(
        self,
        session_factory: Any | None = None,
        *,
        max_cached_sessions: int = 128,
        knowledge_graph: Any | None = None,
    ) -> None:
        self._session_factory = session_factory or (lambda task_id: SessionMemory(task_id=str(task_id)))
        self._max_cached_sessions = max(1, max_cached_sessions)
        self._sessions: OrderedDict[str, Any] = OrderedDict()
        self._knowledge_graph = knowledge_graph

    def _get_session(self, task_id: str) -> Any:
        session = self._sessions.get(task_id)
        if session is not None:
            self._sessions.move_to_end(task_id)
            return session

        session = self._session_factory(task_id)
        self._sessions[task_id] = session
        if len(self._sessions) > self._max_cached_sessions:
            self._sessions.popitem(last=False)
        return session

    def _build_query(self, agent: BaseAgent, ctx: dict[str, Any]) -> str:
        payload = ctx.get("payload", {})
        if agent.role == "writer":
            return (
                f"chapter {payload.get('chapter_index', '')}: "
                f"{payload.get('chapter_title', ctx.get('title', ''))}"
            ).strip()
        if agent.role == "reviewer":
            return (
                f"review chapter {payload.get('chapter_index', '')}: "
                f"{payload.get('chapter_title', ctx.get('title', ''))}"
            ).strip()
        if agent.role == "consistency":
            return "cross chapter consistency and terminology summary"
        return str(ctx.get("title", "task memory context")).strip()

    def _format_rows(self, rows: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for row in rows:
            content = str(row.get("content", "")).strip()
            if content:
                parts.append(content)
        return "\n".join(parts)

    def _build_store_metadata(self, agent: BaseAgent, ctx: dict[str, Any], result: str) -> dict[str, Any]:
        payload = ctx.get("payload", {})
        metadata: dict[str, Any] = {
            "role": agent.role,
            "node_id": ctx.get("node_id", ""),
            "title": ctx.get("title", ""),
        }
        if agent.role in {"writer", "reviewer"}:
            metadata["chapter_index"] = payload.get("chapter_index", "")
            metadata["chapter_title"] = payload.get("chapter_title", "")
        if agent.role == "writer":
            metadata["assigned_evidence"] = payload.get("assigned_evidence", [])
        if agent.role == "consistency":
            metadata["issue_family"] = "document_consistency"
        metadata["summary"] = result[:500]
        return metadata

    def _inject_kg_context(
        self,
        *,
        agent: BaseAgent,
        ctx: dict[str, Any],
        target: dict[str, Any],
    ) -> None:
        if self._knowledge_graph is None or agent.role not in {"outline", "writer"}:
            return

        try:
            kg_rows = self._knowledge_graph.query(self._build_query(agent, ctx))
            target["kg_context"] = "\n".join(e.content for e in kg_rows if e.content)
        except Exception:
            target["kg_context"] = ""

    async def before_task(self, agent: BaseAgent, ctx: dict[str, Any]) -> dict[str, Any]:
        task_id = str(ctx.get("task_id", "")).strip()
        if not task_id:
            return {**ctx, "memory_context": ""}

        try:
            session = self._get_session(task_id)
            enabled = await session.initialize()
            if not enabled:
                base = {**ctx, "_memory_session": session, "memory_context": ""}
                self._inject_kg_context(agent=agent, ctx=ctx, target=base)
                return base

            rows = await session.query(self._build_query(agent, ctx), limit=5)
            result_ctx = {
                **ctx,
                "_memory_session": session,
                "memory_context": self._format_rows(rows),
            }
            self._inject_kg_context(agent=agent, ctx=ctx, target=result_ctx)
            return result_ctx
        except Exception:
            logger.opt(exception=True).warning(
                "memory preload failed, continuing without injected memory context"
            )
            return {**ctx, "memory_context": ""}

    async def after_task(self, agent: BaseAgent, ctx: dict[str, Any], result: str) -> str:
        try:
            session = ctx.get("_memory_session")
            if session is None:
                task_id = str(ctx.get("task_id", "")).strip()
                if not task_id:
                    return result
                session = self._get_session(task_id)
            enabled = await session.initialize()
            if not enabled:
                return result

            metadata = self._build_store_metadata(agent, ctx, result)
            await session.store(result, metadata=metadata)
            if agent.role == "outline":
                await session.store_territory_map(result)
        except Exception:
            logger.opt(exception=True).warning(
                "memory persistence failed, preserving task result without memory side effects"
            )
        return result

DEFAULT_MIDDLEWARES: tuple[AgentMiddleware, ...] = (
    LoggingMiddleware(),
    TokenTrackingMiddleware(),
    TimeoutMiddleware(),
    ContextSummaryMiddleware(),
    MemoryMiddleware(),
)
