"""State store coordination boundary for task and node state updates."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.task_node import TaskNode
from app.services import communicator
from app.services.checkpoint_control import normalize_checkpoint_data


class StateTransitionConflictError(Exception):
    """Raised when task state transition loses optimistic-lock race."""


class ConcurrentModificationError(Exception):
    """Raised when node update loses optimistic-lock race."""


class StateStore:
    """Single coordination boundary for FSM and node state writes."""

    def __init__(
        self,
        *,
        event_sender: Callable[..., Awaitable[Any]] | None = None,
    ) -> None:
        self._event_sender = event_sender or communicator.send_task_event

    async def get_task_state(
        self,
        *,
        session: AsyncSession,
        task_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        task = await session.get(Task, task_id)
        if task is None:
            return None
        if not isinstance(task, Task):
            return {
                "id": task_id,
                "status": "",
                "fsm_state": "",
                "checkpoint_data": normalize_checkpoint_data(None),
            }
        return {
            "id": task.id,
            "status": str(task.status or ""),
            "fsm_state": str(task.fsm_state or ""),
            "checkpoint_data": normalize_checkpoint_data(task.checkpoint_data),
        }

    async def append_transition_log(
        self,
        *,
        checkpoint_data: dict[str, Any] | None,
        from_state: str,
        to_state: str,
        reason: str,
        created_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        checkpoint = normalize_checkpoint_data(checkpoint_data)
        logs = checkpoint.get("transition_logs")
        log_items = list(logs) if isinstance(logs, list) else []
        log_items.append(
            {
                "from_state": from_state,
                "to_state": to_state,
                "reason": reason,
                "metadata": metadata or {},
                "created_by": created_by,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        # Keep bounded payload size.
        checkpoint["transition_logs"] = log_items[-200:]
        return checkpoint

    async def transition_fsm(
        self,
        *,
        session: AsyncSession,
        task_id: uuid.UUID,
        from_state: str,
        to_state: str,
        reason: str,
        created_by: str = "system",
        metadata: dict[str, Any] | None = None,
        checkpoint_data: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> None:
        state = await self.get_task_state(session=session, task_id=task_id)
        if state is None:
            raise ValueError(f"Task {task_id} not found")
        current_state = str(state["fsm_state"] or "")
        if current_state and current_state != from_state:
            raise StateTransitionConflictError(
                f"Task {task_id} transition conflict: expected={from_state}, actual={current_state}"
            )

        merged_checkpoint = await self.append_transition_log(
            checkpoint_data=checkpoint_data or state["checkpoint_data"],
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            created_by=created_by,
            metadata=metadata,
        )
        merged_checkpoint["fsm_state"] = to_state

        result = await session.execute(
            update(Task)
            .where(Task.id == task_id, Task.fsm_state == from_state)
            .values(
                fsm_state=to_state,
                checkpoint_data=merged_checkpoint,
            )
        )
        rowcount = getattr(result, "rowcount", 1)
        if isinstance(rowcount, int) and rowcount != 1:
            raise StateTransitionConflictError(
                f"Task {task_id} transition lost race: {from_state} -> {to_state}"
            )

        if commit:
            await session.commit()
        else:
            await session.flush()

        try:
            await self._event_sender(
                task_id=task_id,
                msg_type="state_transition",
                payload={
                    "from_state": from_state,
                    "to_state": to_state,
                    "reason": reason,
                    "metadata": metadata or {},
                    "created_by": created_by,
                },
            )
        except Exception:
            # Event emission is best-effort and must not break DB consistency.
            pass

    async def update_node_status(
        self,
        *,
        session: AsyncSession,
        node_id: uuid.UUID,
        expected_version: int,
        values: dict[str, Any],
        expected_status: str | None = None,
        expected_assigned_agent: uuid.UUID | None = None,
        commit: bool = True,
    ) -> int:
        stmt = update(TaskNode).where(
            TaskNode.id == node_id,
            TaskNode.version == expected_version,
        )
        if expected_status is not None:
            stmt = stmt.where(TaskNode.status == expected_status)
        if expected_assigned_agent is not None:
            stmt = stmt.where(TaskNode.assigned_agent == expected_assigned_agent)
        next_values = dict(values)
        next_values["version"] = expected_version + 1
        result = await session.execute(stmt.values(**next_values))
        rowcount = getattr(result, "rowcount", 1)
        if isinstance(rowcount, int) and rowcount != 1:
            raise ConcurrentModificationError(
                f"TaskNode {node_id} concurrent modification detected"
            )
        if commit:
            await session.commit()
        else:
            await session.flush()
        return expected_version + 1
