"""Agent 抽象基类 — Redis Streams 消费、心跳上报、中间件管道、任务处理

所有 Layer 0/1/2 Agent 都继承此基类。
Agent 以 asyncio 协程运行于 FastAPI 进程内。
"""

from __future__ import annotations

import asyncio
import re
import uuid
from abc import ABC, abstractmethod
from typing import Any

from app.agents.middleware import AgentMiddleware, DEFAULT_MIDDLEWARES
from app.services import communicator
from app.services.heartbeat import send_heartbeat
from app.services.redis_streams import MessageEnvelope
from app.services.writer_output import extract_writer_markdown
from app.utils.llm_client import BaseLLMClient
from app.utils.logger import logger
from app.utils.token_tracker import TokenTracker


# 心跳间隔（秒）
HEARTBEAT_INTERVAL = 10


class BaseAgent(ABC):
    """Agent 抽象基类

    职责：
    1. 从 Redis Streams inbox 消费任务消息
    2. 定期发送心跳
    3. 通过中间件管道执行任务
    4. 将结果上报给调度器
    """

    def __init__(
        self,
        *,
        agent_id: uuid.UUID,
        name: str,
        role: str,
        layer: int,
        llm_client: BaseLLMClient,
        token_tracker: TokenTracker | None = None,
        middlewares: tuple[AgentMiddleware, ...] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.layer = layer
        self.llm_client = llm_client
        self.token_tracker = token_tracker
        self.middlewares: tuple[AgentMiddleware, ...] = (
            middlewares if middlewares is not None else DEFAULT_MIDDLEWARES
        )

        self._stop = asyncio.Event()
        self._log = logger.bind(agent_id=str(agent_id), agent_role=role)
        self._consume_errors = 0
        self._heartbeat_status = "idle"
        self._heartbeat_task = ""
        self._heartbeat_node = ""

    # ------------------------------------------------------------------
    # 子类必须实现
    # ------------------------------------------------------------------

    @abstractmethod
    async def handle_task(self, ctx: dict[str, Any]) -> str:
        """处理单个任务 — 子类实现具体逻辑。

        Args:
            ctx: 任务上下文，包含 task_id, node_id, title, payload 等

        Returns:
            任务结果文本
        """

    # ------------------------------------------------------------------
    # 中间件管道
    # ------------------------------------------------------------------

    async def process_task(self, ctx: dict[str, Any]) -> str:
        """通过中间件管道执行任务。"""
        # 前置中间件链
        current_ctx = ctx
        for mw in self.middlewares:
            current_ctx = await mw.before_task(self, current_ctx)

        try:
            # 执行超时控制
            timeout = current_ctx.get("_timeout_seconds", 120.0)
            async with asyncio.timeout(timeout):
                result = await self.handle_task(current_ctx)

            # 后置中间件链（逆序）
            for mw in reversed(self.middlewares):
                result = await mw.after_task(self, current_ctx, result)

            return result

        except TimeoutError:
            for mw in self.middlewares:
                await mw.on_error(self, current_ctx, TimeoutError("Task execution timeout"))
            raise

        except Exception as exc:
            for mw in self.middlewares:
                await mw.on_error(self, current_ctx, exc)
            raise

    # ------------------------------------------------------------------
    # 消息处理
    # ------------------------------------------------------------------

    async def _publish_heartbeat(
        self,
        *,
        status: str,
        current_task: Any = "",
        current_node: Any = "",
    ) -> None:
        self._heartbeat_status = status
        self._heartbeat_task = str(current_task or "")
        self._heartbeat_node = str(current_node or "")
        await send_heartbeat(
            self.agent_id,
            status=self._heartbeat_status,
            current_task=self._heartbeat_task,
            current_node=self._heartbeat_node,
        )

    def _chunk_preview_text(self, text: str, *, max_chars: int = 500) -> list[str]:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        if not paragraphs:
            stripped = text.strip()
            return [stripped[:max_chars]] if stripped else []

        chunks: list[str] = []
        for paragraph in paragraphs:
            if len(paragraph) <= max_chars:
                chunks.append(paragraph)
                continue
            for start in range(0, len(paragraph), max_chars):
                chunks.append(paragraph[start:start + max_chars].strip())
        return [chunk for chunk in chunks if chunk]

    def _extract_review_score(self, text: str) -> int | None:
        match = re.search(r"\bscore\b\D*(\d{1,3})", text, flags=re.IGNORECASE)
        if not match:
            return None
        value = int(match.group(1))
        if 0 <= value <= 100:
            return value
        return None

    async def _emit_task_event(
        self,
        *,
        task_id: str,
        node_id: str,
        msg_type: str,
        payload: dict[str, Any],
    ) -> None:
        try:
            await communicator.send_task_event(
                task_id=task_id,
                node_id=node_id,
                from_agent=str(self.agent_id),
                msg_type=msg_type,
                payload=payload,
            )
        except Exception:
            self._log.opt(exception=True).warning("task event emission failed: {}", msg_type)

    async def _emit_role_events(
        self,
        *,
        task_id: str,
        node_id: str,
        payload: dict[str, Any],
        result: str,
    ) -> None:
        if self.role == "writer":
            chunks = self._chunk_preview_text(extract_writer_markdown(result))
            for idx, chunk in enumerate(chunks):
                await self._emit_task_event(
                    task_id=task_id,
                    node_id=node_id,
                    msg_type="chapter_preview",
                    payload={
                        "chapter_index": payload.get("chapter_index"),
                        "chapter_title": payload.get("chapter_title", ""),
                        "chunk_index": idx,
                        "content": chunk,
                    },
                )
            return

        if self.role == "reviewer":
            await self._emit_task_event(
                task_id=task_id,
                node_id=node_id,
                msg_type="review_score",
                payload={
                    "chapter_index": payload.get("chapter_index"),
                    "chapter_title": payload.get("chapter_title", ""),
                    "score": self._extract_review_score(result),
                    "review": result,
                },
            )
            return

        if self.role == "consistency":
            await self._emit_task_event(
                task_id=task_id,
                node_id=node_id,
                msg_type="consistency_result",
                payload={"result": result},
            )

    async def _handle_message(self, envelope: MessageEnvelope) -> None:
        """处理从 inbox 消费到的一条消息。"""
        task_id = envelope.task_id
        node_id = envelope.node_id
        payload = envelope.payload

        ctx: dict[str, Any] = {
            "task_id": task_id,
            "node_id": node_id,
            "title": payload.get("title", ""),
            "agent_role": payload.get("agent_role", self.role),
            "retry_count": payload.get("retry_count", 0),
            "payload": payload,
        }

        # 更新心跳为 busy
        await self._publish_heartbeat(
            status="busy",
            current_task=task_id,
            current_node=node_id,
        )

        try:
            result = await self.process_task(ctx)

            # 上报成功结果
            await communicator.send_task_result(
                task_id=task_id,
                node_id=node_id,
                from_agent=str(self.agent_id),
                result={"status": "done", "output": result},
            )
            await self._emit_role_events(
                task_id=task_id,
                node_id=node_id,
                payload=payload,
                result=result,
            )

            self._log.bind(task_id=task_id, node_id=node_id).info(
                "task result reported: done"
            )

        except Exception as exc:
            # 上报失败
            await communicator.send_task_result(
                task_id=task_id,
                node_id=node_id,
                from_agent=str(self.agent_id),
                result={"status": "failed", "error": str(exc)},
            )

            self._log.bind(task_id=task_id, node_id=node_id).error(
                "task result reported: failed — {}", exc,
            )

        finally:
            # 恢复心跳为 idle
            await self._publish_heartbeat(status="idle")

    # ------------------------------------------------------------------
    # 主运行循环
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Agent 主循环 — 消费消息 + 心跳。"""
        self._log.info("agent started: {} (layer={})", self.name, self.layer)

        # 初始心跳
        await self._publish_heartbeat(status="idle")

        # 并行运行：消费循环 + 心跳循环
        try:
            await asyncio.gather(
                self._consume_loop(),
                self._heartbeat_loop(),
            )
        except asyncio.CancelledError:
            self._log.info("agent cancelled")
        finally:
            await self._publish_heartbeat(status="offline")
            self._log.info("agent stopped: {}", self.name)

    async def _consume_loop(self) -> None:
        """持续从 inbox 消费消息。"""
        consumer_name = f"{self.role}_{self.agent_id}"

        while not self._stop.is_set():
            try:
                messages = await communicator.consume_agent_inbox(
                    self.agent_id,
                    consumer_name,
                    count=1,
                    block=2000,
                )

                for msg in messages:
                    envelope = MessageEnvelope.from_redis(msg.data)
                    await self._handle_message(envelope)

                    # ACK 消息
                    await communicator.ack_agent_message(
                        self.agent_id, msg.message_id,
                    )

                # 成功消费后重置退避计数器
                self._consume_errors = 0

            except asyncio.CancelledError:
                raise
            except Exception:
                self._log.opt(exception=True).error("consume loop error")
                # 指数退避：最多 30 秒
                backoff = min(2 ** self._consume_errors, 30)
                self._consume_errors += 1
                await asyncio.sleep(backoff)

    async def _heartbeat_loop(self) -> None:
        """定期发送心跳。"""
        while not self._stop.is_set():
            try:
                await self._publish_heartbeat(
                    status=self._heartbeat_status,
                    current_task=self._heartbeat_task,
                    current_node=self._heartbeat_node,
                )
            except Exception:
                self._log.opt(exception=True).warning("heartbeat failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=HEARTBEAT_INTERVAL)
                break  # stop event was set
            except TimeoutError:
                pass  # normal heartbeat cycle

    def stop(self) -> None:
        """请求停止 Agent。"""
        self._stop.set()
