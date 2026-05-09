"""Task control service for pause/resume/skip/retry commands."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.task import Task
from app.models.task_node import TaskNode
from app.schemas.task import TaskDetailRead
from app.services.checkpoint_control import ensure_task_control
from app.services import communicator, task_service
from app.services.dag_scheduler import get_scheduler, start_scheduler
from app.services.long_text_fsm import LongTextState
from app.services.redis_streams import remove_timeout_watch, timeout_watch_member
from app.services.state_store import StateStore, StateTransitionConflictError
from app.utils.logger import logger

PAUSABLE_TASK_STATUSES = {"pending", "running"}
SKIPPABLE_NODE_STATUSES = {"pending", "ready", "running"}
RETRYABLE_NODE_STATUSES = {"failed", "skipped"}
TERMINAL_TASK_STATUSES = {"done", "completed", "failed", "cancelled", "canceled"}


class TaskControlError(Exception):
    """Raised when a control command is illegal for current task/node state."""


class TaskControlNotFoundError(Exception):
    """Raised when a task is missing or not visible to the caller."""


def _ensure_checkpoint_and_control(task: Any) -> dict[str, Any]:
    return ensure_task_control(task)


def _merge_control_update(
    task: Any,
    *,
    status: str | None = None,
    command_type: str | None = None,
    node_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    control = _ensure_checkpoint_and_control(task)
    if status is not None:
        control["status"] = status
    if command_type is not None:
        command: dict[str, str] = {"type": command_type}
        if node_id is not None:
            command["node_id"] = str(node_id)
        control["last_command"] = command
    task.checkpoint_data["control"] = control
    return control


def ensure_pause_allowed(task: Any) -> None:
    status = str(getattr(task, "status", "") or "")
    if status not in PAUSABLE_TASK_STATUSES:
        raise TaskControlError(f"pause not allowed for task status '{status}'")
    control = _ensure_checkpoint_and_control(task)
    control_status = str(control.get("status", "") or "")
    if control_status != "active":
        raise TaskControlError(
            f"pause not allowed for control status '{control_status}'"
        )


def ensure_resume_allowed(task: Any) -> None:
    _ensure_task_not_terminal(task, action="resume")
    control = _ensure_checkpoint_and_control(task)
    control_status = str(control.get("status", ""))
    if control_status != "paused":
        raise TaskControlError(
            f"resume not allowed for control status '{control_status}'"
        )


def _ensure_task_not_terminal(task: Any, *, action: str) -> None:
    status = str(getattr(task, "status", "") or "")
    if status in TERMINAL_TASK_STATUSES:
        raise TaskControlError(f"{action} not allowed for task status '{status}'")


def _get_node_or_raise(task: Any, node_id: uuid.UUID | None) -> Any:
    if node_id is None:
        raise TaskControlError("node_id is required")

    for node in list(getattr(task, "nodes", []) or []):
        if getattr(node, "id", None) == node_id:
            return node
    raise TaskControlError(f"node '{node_id}' not found on task")


def _skip_node_in_memory(task: Any, *, node_id: uuid.UUID | None) -> Any:
    node = _get_node_or_raise(task, node_id)
    status = str(getattr(node, "status", "") or "")
    if status not in SKIPPABLE_NODE_STATUSES:
        raise TaskControlError(
            f"skip not allowed for node status '{status}'"
        )

    node.status = "skipped"
    node.assigned_agent = None
    _merge_control_update(task, command_type="skip", node_id=node.id)
    return node


def _retry_node_in_memory(task: Any, *, node_id: uuid.UUID | None) -> Any:
    node = _get_node_or_raise(task, node_id)
    status = str(getattr(node, "status", "") or "")
    if status not in RETRYABLE_NODE_STATUSES:
        raise TaskControlError(
            f"retry not allowed for node status '{status}'"
        )
    if status == "skipped" and _dependents_progressed(task, node):
        raise TaskControlError("retry not allowed after dependent progress")

    next_status = "ready"
    if status == "skipped" and not _dependencies_satisfied(task, node):
        next_status = "pending"

    node.status = next_status
    node.started_at = None
    node.finished_at = None
    node.result = None
    node.assigned_agent = None
    # Manual retry should start a fresh scheduler retry budget.
    node.retry_count = 0
    _merge_control_update(task, command_type="retry", node_id=node.id)
    return node


async def _wake_scheduler(task_id: uuid.UUID) -> None:
    scheduler = get_scheduler(task_id)
    if scheduler is not None:
        scheduler.wake()
        return
    await start_scheduler(task_id)


def _dependencies_satisfied(task: Any, node: Any) -> bool:
    deps = list(getattr(node, "depends_on", []) or [])
    if not deps:
        return True

    statuses = {
        str(getattr(candidate, "id", "")): str(getattr(candidate, "status", "") or "")
        for candidate in list(getattr(task, "nodes", []) or [])
    }
    return all(statuses.get(str(dep)) in {"done", "skipped"} for dep in deps)


def _dependents_progressed(task: Any, node: Any) -> bool:
    node_id = str(getattr(node, "id", "") or "")
    for candidate in list(getattr(task, "nodes", []) or []):
        deps = {str(dep) for dep in list(getattr(candidate, "depends_on", []) or [])}
        if node_id not in deps:
            continue
        if str(getattr(candidate, "status", "") or "") != "pending":
            return True
    return False


async def _reconcile_running_skip(task_id: uuid.UUID, node: Any) -> None:
    if str(getattr(node, "status", "") or "") != "skipped":
        return

    scheduler = get_scheduler(task_id)
    if scheduler is None:
        return

    await scheduler.reconcile_skipped_node(node.id)


async def _cleanup_orphaned_running_skip(
    session: AsyncSession,
    *,
    task_id: uuid.UUID,
    node_id: uuid.UUID,
    assigned_agent_id: uuid.UUID | None,
) -> None:
    await remove_timeout_watch(timeout_watch_member(task_id, node_id))
    await remove_timeout_watch(str(node_id))
    if assigned_agent_id is not None:
        await session.execute(
            update(Agent)
            .where(Agent.id == assigned_agent_id)
            .values(status="idle")
        )


async def _reconcile_running_skip_with_fallback(
    session: AsyncSession | None,
    task_id: uuid.UUID,
    node_id: uuid.UUID,
    *,
    was_running: bool,
    assigned_agent_id: uuid.UUID | None,
) -> None:
    scheduler = get_scheduler(task_id)
    if scheduler is None:
        if not was_running:
            return
        if session is not None:
            await _cleanup_orphaned_running_skip(
                session,
                task_id=task_id,
                node_id=node_id,
                assigned_agent_id=assigned_agent_id,
            )
            await session.commit()
        return

    await scheduler.reconcile_skipped_node(node_id)


async def _emit_control_events(
    *,
    task_id: uuid.UUID,
    command_type: str,
    control: dict[str, Any],
    message: str,
    node: Any | None = None,
) -> None:
    try:
        node_id = str(getattr(node, "id", "") or "")
        if node is not None:
            await communicator.send_status_update(
                task_id=task_id,
                node_id=node_id,
                status=str(getattr(node, "status", "") or ""),
                from_agent="task_control",
                extra={"command": command_type},
            )

        await communicator.send_task_event(
            task_id=task_id,
            from_agent="task_control",
            msg_type="dag_update",
            payload={"control": dict(control)},
        )
        await communicator.send_task_event(
            task_id=task_id,
            node_id=node_id,
            from_agent="task_control",
            msg_type="log",
            payload={
                "level": "info",
                "message": message,
                "command": command_type,
                "node_id": node_id or None,
            },
        )
    except Exception:
        logger.bind(task_id=str(task_id), command_type=command_type).opt(
            exception=True
        ).warning("failed to emit control monitor events")


async def _emit_operator_action_event(
    *,
    task_id: uuid.UUID,
    action: str,
    reason: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        await communicator.send_task_event(
            task_id=task_id,
            from_agent="task_control",
            msg_type="operator_action",
            payload={
                "action": action,
                "reason": reason,
                "metadata": dict(metadata or {}),
            },
        )
    except Exception:
        logger.bind(task_id=str(task_id), action=action).opt(exception=True).warning(
            "failed to emit operator action event"
        )


async def _get_visible_task(
    session: AsyncSession,
    task_id: uuid.UUID,
    *,
    user_id: str,
    is_admin: bool,
) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise TaskControlNotFoundError("Task not found")
    if not task_service.task_visible_to_user(
        task, user_id=user_id, is_admin=is_admin
    ):
        raise TaskControlNotFoundError("Task not found")
    return task


async def _load_task_nodes(
    session: AsyncSession,
    task_id: uuid.UUID,
) -> list[TaskNode]:
    result = await session.execute(
        select(TaskNode)
        .where(TaskNode.task_id == task_id)
        .order_by(TaskNode.id)
    )
    return list(result.scalars().all())


async def _get_persisted_node_or_raise(
    session: AsyncSession,
    task_id: uuid.UUID,
    node_id: uuid.UUID,
) -> TaskNode:
    result = await session.execute(
        select(TaskNode).where(
            TaskNode.task_id == task_id,
            TaskNode.id == node_id,
        )
    )
    node = result.scalars().first()
    if node is None:
        raise TaskControlError(f"node '{node_id}' not found on task")
    return node


async def _raise_node_state_conflict(
    session: AsyncSession,
    task_id: uuid.UUID,
    node_id: uuid.UUID,
    *,
    action: str,
) -> None:
    current = await _get_persisted_node_or_raise(session, task_id, node_id)
    raise TaskControlError(
        f"{action} not allowed for node status '{str(getattr(current, 'status', '') or '')}'"
    )


async def _commit_and_refresh_detail(
    session: AsyncSession,
    task_id: uuid.UUID,
    *,
    user_id: str,
    is_admin: bool,
) -> TaskDetailRead:
    await session.commit()
    detail = await task_service.get_task_detail(
        session,
        task_id,
        user_id=user_id,
        is_admin=is_admin,
    )
    if detail is None:
        raise TaskControlNotFoundError("Task not found")
    return detail


async def pause_task(
    session: AsyncSession,
    task_id: uuid.UUID,
    *,
    user_id: str,
    is_admin: bool,
) -> TaskDetailRead:
    """Request cooperative pause. Scheduler later promotes pause_requested -> paused."""
    task = await _get_visible_task(
        session,
        task_id,
        user_id=user_id,
        is_admin=is_admin,
    )
    ensure_pause_allowed(task)
    _merge_control_update(task, status="pause_requested", command_type="pause")
    detail = await _commit_and_refresh_detail(
        session,
        task_id,
        user_id=user_id,
        is_admin=is_admin,
    )
    await _emit_control_events(
        task_id=task_id,
        command_type="pause",
        control=dict(task.checkpoint_data["control"]),
        message="pause requested",
    )
    await _wake_scheduler(task_id)
    return detail


async def resume_task(
    session: AsyncSession,
    task_id: uuid.UUID,
    *,
    user_id: str,
    is_admin: bool,
) -> TaskDetailRead:
    task = await _get_visible_task(
        session,
        task_id,
        user_id=user_id,
        is_admin=is_admin,
    )
    ensure_resume_allowed(task)
    _merge_control_update(task, status="active", command_type="resume")
    detail = await _commit_and_refresh_detail(
        session,
        task_id,
        user_id=user_id,
        is_admin=is_admin,
    )
    await _emit_control_events(
        task_id=task_id,
        command_type="resume",
        control=dict(task.checkpoint_data["control"]),
        message="task resumed",
    )
    await _wake_scheduler(task_id)
    return detail


async def skip_node(
    session: AsyncSession,
    task_id: uuid.UUID,
    *,
    node_id: uuid.UUID,
    user_id: str,
    is_admin: bool,
) -> TaskDetailRead:
    task = await _get_visible_task(
        session,
        task_id,
        user_id=user_id,
        is_admin=is_admin,
    )
    _ensure_task_not_terminal(task, action="skip")
    node_before_skip = await _get_persisted_node_or_raise(session, task_id, node_id)
    status_before_skip = str(getattr(node_before_skip, "status", "") or "")
    if status_before_skip not in SKIPPABLE_NODE_STATUSES:
        raise TaskControlError(
            f"skip not allowed for node status '{status_before_skip}'"
        )
    assigned_agent_id = getattr(node_before_skip, "assigned_agent", None)
    was_running = status_before_skip == "running"
    control = _merge_control_update(task, command_type="skip", node_id=node_id)
    skip_stmt = (
        update(TaskNode)
        .where(
            TaskNode.task_id == task_id,
            TaskNode.id == node_id,
            TaskNode.status == status_before_skip,
        )
        .values(status="skipped", assigned_agent=None)
    )
    if status_before_skip == "running":
        skip_stmt = skip_stmt.where(TaskNode.assigned_agent == assigned_agent_id)
    skip_result = await session.execute(skip_stmt)
    if skip_result.rowcount != 1:
        await _raise_node_state_conflict(
            session,
            task_id,
            node_id,
            action="skip",
        )
    detail = await _commit_and_refresh_detail(
        session,
        task_id,
        user_id=user_id,
        is_admin=is_admin,
    )
    try:
        await _reconcile_running_skip_with_fallback(
            session,
            task_id,
            node_id,
            was_running=was_running,
            assigned_agent_id=assigned_agent_id,
        )
    except Exception:
        logger.bind(task_id=str(task_id), node_id=str(node_id)).opt(
            exception=True
        ).warning("post-commit skip reconciliation failed")
    await _emit_control_events(
        task_id=task_id,
        command_type="skip",
        control=dict(control),
        node=SimpleNamespace(id=node_id, status="skipped"),
        message="node skipped",
    )
    await _wake_scheduler(task_id)
    return detail


async def retry_node(
    session: AsyncSession,
    task_id: uuid.UUID,
    *,
    node_id: uuid.UUID,
    user_id: str,
    is_admin: bool,
) -> TaskDetailRead:
    task = await _get_visible_task(
        session,
        task_id,
        user_id=user_id,
        is_admin=is_admin,
    )
    _ensure_task_not_terminal(task, action="retry")
    task_state = SimpleNamespace(
        nodes=await _load_task_nodes(session, task_id),
        checkpoint_data=task.checkpoint_data,
    )
    node_before_retry = _get_node_or_raise(task_state, node_id)
    status_before_retry = str(getattr(node_before_retry, "status", "") or "")
    if status_before_retry not in RETRYABLE_NODE_STATUSES:
        raise TaskControlError(
            f"retry not allowed for node status '{status_before_retry}'"
        )
    if status_before_retry == "skipped" and _dependents_progressed(task_state, node_before_retry):
        raise TaskControlError("retry not allowed after dependent progress")

    next_status = "ready"
    if status_before_retry == "skipped" and not _dependencies_satisfied(task_state, node_before_retry):
        next_status = "pending"

    control = _merge_control_update(task, command_type="retry", node_id=node_id)
    retry_stmt = (
        update(TaskNode)
        .where(
            TaskNode.task_id == task_id,
            TaskNode.id == node_id,
            TaskNode.status == status_before_retry,
            TaskNode.retry_count == getattr(node_before_retry, "retry_count", 0),
        )
        .values(
            status=next_status,
            started_at=None,
            finished_at=None,
            result=None,
            assigned_agent=None,
            retry_count=0,
        )
    )
    retry_result = await session.execute(retry_stmt)
    if retry_result.rowcount != 1:
        await _raise_node_state_conflict(
            session,
            task_id,
            node_id,
            action="retry",
        )
    detail = await _commit_and_refresh_detail(
        session,
        task_id,
        user_id=user_id,
        is_admin=is_admin,
    )
    await _emit_control_events(
        task_id=task_id,
        command_type="retry",
        control=dict(control),
        node=SimpleNamespace(id=node_id, status=next_status),
        message="node retried",
    )
    await _wake_scheduler(task_id)
    return detail


async def admin_force_transition(
    session: AsyncSession,
    task_id: uuid.UUID,
    *,
    to_state: str,
    reason: str,
    user_id: str,
    is_admin: bool,
) -> TaskDetailRead:
    if not is_admin:
        raise TaskControlError("admin privileges required")
    task = await _get_visible_task(
        session,
        task_id,
        user_id=user_id,
        is_admin=is_admin,
    )
    target_state = str(to_state or "").strip().lower()
    valid_states = {state.value for state in LongTextState}
    if target_state not in valid_states:
        raise TaskControlError(f"invalid target state '{target_state}'")

    current_state = str(getattr(task, "fsm_state", "") or "init").strip().lower() or "init"
    checkpoint_data = (
        dict(task.checkpoint_data)
        if isinstance(task.checkpoint_data, dict)
        else {}
    )
    checkpoint_data.setdefault("operator_actions", []).append(
        {
            "action": "force_transition",
            "from_state": current_state,
            "to_state": target_state,
            "reason": reason,
        }
    )
    state_store = StateStore()
    try:
        await state_store.transition_fsm(
            session=session,
            task_id=task_id,
            from_state=current_state,
            to_state=target_state,
            reason=f"admin_force_transition:{reason}",
            created_by=user_id or "admin",
            metadata={"action": "force_transition"},
            checkpoint_data=checkpoint_data,
            commit=False,
        )
    except StateTransitionConflictError as exc:
        raise TaskControlError(str(exc)) from exc
    detail = await _commit_and_refresh_detail(
        session,
        task_id,
        user_id=user_id,
        is_admin=is_admin,
    )
    await _emit_operator_action_event(
        task_id=task_id,
        action="force_transition",
        reason=reason,
        metadata={"to_state": target_state},
    )
    await _wake_scheduler(task_id)
    return detail


async def admin_resume_from_checkpoint(
    session: AsyncSession,
    task_id: uuid.UUID,
    *,
    reason: str,
    user_id: str,
    is_admin: bool,
) -> TaskDetailRead:
    if not is_admin:
        raise TaskControlError("admin privileges required")
    task = await _get_visible_task(
        session,
        task_id,
        user_id=user_id,
        is_admin=is_admin,
    )
    control = _merge_control_update(task, status="active", command_type="resume_from_checkpoint")
    if str(getattr(task, "status", "") or "") in TERMINAL_TASK_STATUSES:
        task.status = "pending"
    detail = await _commit_and_refresh_detail(
        session,
        task_id,
        user_id=user_id,
        is_admin=is_admin,
    )
    await _emit_operator_action_event(
        task_id=task_id,
        action="resume_from_checkpoint",
        reason=reason,
        metadata={"control_status": control.get("status")},
    )
    await _emit_control_events(
        task_id=task_id,
        command_type="resume_from_checkpoint",
        control=dict(control),
        message="resume from checkpoint requested",
    )
    await _wake_scheduler(task_id)
    return detail


async def admin_skip_node(
    session: AsyncSession,
    task_id: uuid.UUID,
    *,
    node_id: uuid.UUID,
    reason: str,
    user_id: str,
    is_admin: bool,
) -> TaskDetailRead:
    if not is_admin:
        raise TaskControlError("admin privileges required")
    detail = await skip_node(
        session,
        task_id,
        node_id=node_id,
        user_id=user_id,
        is_admin=is_admin,
    )
    await _emit_operator_action_event(
        task_id=task_id,
        action="skip_node",
        reason=reason,
        metadata={"node_id": str(node_id)},
    )
    return detail


async def admin_retry_node(
    session: AsyncSession,
    task_id: uuid.UUID,
    *,
    node_id: uuid.UUID,
    reason: str,
    user_id: str,
    is_admin: bool,
) -> TaskDetailRead:
    if not is_admin:
        raise TaskControlError("admin privileges required")
    detail = await retry_node(
        session,
        task_id,
        node_id=node_id,
        user_id=user_id,
        is_admin=is_admin,
    )
    await _emit_operator_action_event(
        task_id=task_id,
        action="retry_node",
        reason=reason,
        metadata={"node_id": str(node_id)},
    )
    return detail

