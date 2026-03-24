"""Shared Redis -> WebSocket bridge for per-task monitoring streams."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from app.schemas.ws_event import (
    AgentStatusEvent,
    ChapterPreviewEvent,
    ConsistencyResultEvent,
    DagUpdateEvent,
    LogEvent,
    NodeUpdateEvent,
    ReviewScoreEvent,
    TaskDoneEvent,
    TaskEvent,
)
from app.services.redis_streams import MessageEnvelope, StreamMessage, task_events_key, xread_latest
from app.services.ws_manager import ws_manager
from app.utils.logger import logger

KnownEventFactory = Callable[[MessageEnvelope], TaskEvent]
ReaderFn = Callable[..., Awaitable[list[StreamMessage]]]


def _build_node_update(envelope: MessageEnvelope) -> TaskEvent:
    return NodeUpdateEvent(
        task_id=envelope.task_id,
        node_id=envelope.node_id,
        from_agent=envelope.from_agent,
        timestamp=envelope.timestamp,
        payload=envelope.payload,
    )


def _build_log(envelope: MessageEnvelope) -> TaskEvent:
    return LogEvent(
        task_id=envelope.task_id,
        node_id=envelope.node_id,
        from_agent=envelope.from_agent,
        timestamp=envelope.timestamp,
        payload=envelope.payload,
    )


def _build_agent_status(envelope: MessageEnvelope) -> TaskEvent:
    return AgentStatusEvent(
        task_id=envelope.task_id,
        node_id=envelope.node_id,
        from_agent=envelope.from_agent,
        timestamp=envelope.timestamp,
        payload=envelope.payload,
    )


def _build_task_done(envelope: MessageEnvelope) -> TaskEvent:
    return TaskDoneEvent(
        task_id=envelope.task_id,
        node_id=envelope.node_id,
        from_agent=envelope.from_agent,
        timestamp=envelope.timestamp,
        payload=envelope.payload,
    )


def _build_chapter_preview(envelope: MessageEnvelope) -> TaskEvent:
    return ChapterPreviewEvent(
        task_id=envelope.task_id,
        node_id=envelope.node_id,
        from_agent=envelope.from_agent,
        timestamp=envelope.timestamp,
        payload=envelope.payload,
    )


def _build_review_score(envelope: MessageEnvelope) -> TaskEvent:
    return ReviewScoreEvent(
        task_id=envelope.task_id,
        node_id=envelope.node_id,
        from_agent=envelope.from_agent,
        timestamp=envelope.timestamp,
        payload=envelope.payload,
    )


def _build_consistency_result(envelope: MessageEnvelope) -> TaskEvent:
    return ConsistencyResultEvent(
        task_id=envelope.task_id,
        node_id=envelope.node_id,
        from_agent=envelope.from_agent,
        timestamp=envelope.timestamp,
        payload=envelope.payload,
    )


def _build_dag_update(envelope: MessageEnvelope) -> TaskEvent:
    return DagUpdateEvent(
        task_id=envelope.task_id,
        node_id=envelope.node_id,
        from_agent=envelope.from_agent,
        timestamp=envelope.timestamp,
        payload=envelope.payload,
    )


EVENT_BUILDERS: dict[str, KnownEventFactory] = {
    "status_update": _build_node_update,
    "node_update": _build_node_update,
    "log": _build_log,
    "agent_status": _build_agent_status,
    "task_done": _build_task_done,
    "chapter_preview": _build_chapter_preview,
    "review_score": _build_review_score,
    "consistency_result": _build_consistency_result,
    "dag_update": _build_dag_update,
}


def normalize_task_event(message: StreamMessage) -> TaskEvent | None:
    envelope = MessageEnvelope.from_redis(message.data)
    builder = EVENT_BUILDERS.get(envelope.msg_type)
    if builder is None:
        logger.bind(stream=message.stream, msg_type=envelope.msg_type).warning(
            "Skipping unsupported task event type"
        )
        return None
    return builder(envelope)


class TaskEventBridge:
    def __init__(
        self,
        *,
        ws_manager=ws_manager,
        reader: ReaderFn = xread_latest,
        block_ms: int = 1000,
        retry_backoff_base: float = 0.1,
        retry_backoff_max: float = 2.0,
    ) -> None:
        self._ws_manager = ws_manager
        self._reader = reader
        self._block_ms = block_ms
        self._retry_backoff_base = max(0.0, retry_backoff_base)
        self._retry_backoff_max = max(self._retry_backoff_base, retry_backoff_max)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._tasks_lock = asyncio.Lock()

    def _compute_backoff(self, failure_count: int) -> float:
        if failure_count <= 0:
            return 0.0
        delay = self._retry_backoff_base * (2 ** (failure_count - 1))
        return min(delay, self._retry_backoff_max)

    async def ensure_started(
        self,
        task_id: str,
        *,
        start_from_id: str = "$",
    ) -> bool:
        async with self._tasks_lock:
            task = self._tasks.get(task_id)
            if task is not None and not task.done():
                return False

            reader_task = asyncio.create_task(
                self._run(task_id, start_from_id=start_from_id),
                name=f"task-event-bridge:{task_id}",
            )
            self._tasks[task_id] = reader_task
            return True

    async def stop(self, task_id: str) -> None:
        async with self._tasks_lock:
            task = self._tasks.pop(task_id, None)
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _run(self, task_id: str, *, start_from_id: str = "$") -> None:
        stream = task_events_key(task_id)
        latest_id = start_from_id
        failure_count = 0
        try:
            while self._ws_manager.get_connections(task_id):
                try:
                    messages = await self._reader(
                        {stream: latest_id},
                        count=50,
                        block=self._block_ms,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    failure_count += 1
                    delay = self._compute_backoff(failure_count)
                    logger.bind(task_id=task_id, delay_s=round(delay, 3)).opt(
                        exception=True
                    ).warning("Task event bridge read failed; retrying")
                    await asyncio.sleep(delay)
                    continue

                if not messages:
                    failure_count = 0
                    continue

                for message in messages:
                    event = normalize_task_event(message)
                    if event is None:
                        latest_id = message.message_id
                        failure_count = 0
                        continue
                    try:
                        await self._ws_manager.broadcast(task_id, event.model_dump())
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        failure_count += 1
                        delay = self._compute_backoff(failure_count)
                        logger.bind(
                            task_id=task_id,
                            message_id=message.message_id,
                            delay_s=round(delay, 3),
                        ).opt(exception=True).warning(
                            "Task event bridge broadcast failed; retrying"
                        )
                        await asyncio.sleep(delay)
                        break

                    latest_id = message.message_id
                    failure_count = 0
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.bind(task_id=task_id).opt(exception=True).error(
                "Task event bridge crashed"
            )
        finally:
            async with self._tasks_lock:
                current = self._tasks.get(task_id)
                if current is asyncio.current_task():
                    self._tasks.pop(task_id, None)


event_bridge = TaskEventBridge()
