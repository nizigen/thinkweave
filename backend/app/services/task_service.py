"""Task service layer for creating, reading, and listing tasks."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.task import Task
from app.models.task_node import TaskNode
from app.schemas.task import TaskCreate, TaskDetailRead, TaskNodeRead, TaskRead
from app.services.entry_stage import build_entry_metadata
from app.services.task_decomposer import TaskValidationError, decompose_task
from app.utils.llm_client import BaseLLMClient
from app.utils.logger import logger


def normalize_checkpoint_data(checkpoint_data: dict[str, Any] | None) -> dict[str, Any]:
    checkpoint = dict(checkpoint_data) if isinstance(checkpoint_data, dict) else {}
    control = checkpoint.get("control")
    control_dict = dict(control) if isinstance(control, dict) else {}
    control_dict.setdefault("status", "active")
    preview_cache = control_dict.get("preview_cache")
    control_dict["preview_cache"] = (
        dict(preview_cache) if isinstance(preview_cache, dict) else {}
    )
    review_scores = control_dict.get("review_scores")
    control_dict["review_scores"] = (
        dict(review_scores) if isinstance(review_scores, dict) else {}
    )
    checkpoint["control"] = control_dict
    return checkpoint


def _apply_monitor_recovery_event(
    task: Task,
    *,
    node_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    checkpoint = normalize_checkpoint_data(task.checkpoint_data)
    control = checkpoint["control"]
    if event_type == "chapter_preview":
        preview_cache = dict(control["preview_cache"])
        preview_cache[node_id] = dict(payload)
        control["preview_cache"] = preview_cache
    elif event_type == "review_score":
        review_scores = dict(control["review_scores"])
        review_scores[node_id] = dict(payload)
        control["review_scores"] = review_scores
    else:
        return
    checkpoint["control"] = control
    task.checkpoint_data = checkpoint


async def create_task(
    session: AsyncSession,
    task_in: TaskCreate,
    llm_client: BaseLLMClient,
    *,
    owner_id: str = "",
) -> TaskDetailRead:
    """
    Create a task, trigger LLM decomposition, persist DAG nodes.

    Flow: create the task row, decompose it via the LLM, persist DAG nodes,
    then return the task detail payload.
    """
    # Persist the task row first so downstream records can reference it.
    entry_meta = build_entry_metadata(
        draft_text=task_in.draft_text,
        review_comments=task_in.review_comments,
    )
    task = Task(
        title=task_in.title,
        mode=task_in.mode,
        depth=task_in.depth,
        target_words=task_in.target_words,
        owner_id=owner_id or None,
        status="decomposing",
        fsm_state=entry_meta["entry_stage"],
        checkpoint_data=entry_meta,
    )
    session.add(task)
    await session.flush()

    logger.bind(task_id=str(task.id), mode=task.mode).info(
        "Task created, starting decomposition"
    )

    # Ask the decomposer for a DAG plan.
    dag = await decompose_task(
        title=task_in.title,
        mode=task_in.mode,
        depth=task_in.depth,
        target_words=task_in.target_words,
        llm_client=llm_client,
    )

    # Map DAG string IDs to database UUID primary keys.
    id_map: dict[str, uuid.UUID] = {}
    nodes: list[TaskNode] = []

    for dag_node in dag.nodes:
        node_uuid = uuid.uuid4()
        id_map[dag_node.id] = node_uuid

    for dag_node in dag.nodes:
        depends_uuids = [id_map[dep] for dep in dag_node.depends_on]
        node = TaskNode(
            id=id_map[dag_node.id],
            task_id=task.id,
            title=dag_node.title,
            agent_role=dag_node.role,
            status="pending",
            depends_on=depends_uuids if depends_uuids else None,
        )
        nodes.append(node)
        session.add(node)

    # Mark the task as ready once all nodes are persisted.
    task.status = "pending"
    await session.flush()
    await session.commit()

    logger.bind(task_id=str(task.id), node_count=len(nodes)).info(
        "DAG nodes persisted"
    )

    # Build the response from the persisted task and node state.
    node_reads = [
        TaskNodeRead(
            id=n.id,
            task_id=n.task_id,
            title=n.title,
            agent_role=n.agent_role,
            assigned_agent=n.assigned_agent,
            status=n.status,
            depends_on=n.depends_on,
            retry_count=n.retry_count,
            started_at=n.started_at,
            finished_at=n.finished_at,
        )
        for n in nodes
    ]
    return TaskDetailRead(
        id=task.id,
        title=task.title,
        mode=task.mode,
        status=task.status,
        fsm_state=task.fsm_state,
        word_count=task.word_count,
        depth=task.depth,
        target_words=task.target_words,
        created_at=task.created_at,
        finished_at=task.finished_at,
        checkpoint_data=normalize_checkpoint_data(task.checkpoint_data),
        nodes=node_reads,
    )


async def get_task_detail(
    session: AsyncSession,
    task_id: uuid.UUID,
    *,
    user_id: str = "",
    is_admin: bool = False,
) -> TaskDetailRead | None:
    """Get a task with its DAG nodes. Returns None if not found."""
    task = await session.get(Task, task_id)
    if task is None:
        return None
    if not task_visible_to_user(task, user_id=user_id, is_admin=is_admin):
        return None

    result = await session.execute(
        select(TaskNode)
        .where(TaskNode.task_id == task_id)
        .order_by(TaskNode.id)
    )
    nodes = list(result.scalars().all())

    node_reads = [
        TaskNodeRead.model_validate(n) for n in nodes
    ]
    task_read = TaskDetailRead.model_validate(task)
    task_read.checkpoint_data = normalize_checkpoint_data(task.checkpoint_data)
    task_read.nodes = node_reads
    return task_read


async def persist_monitor_recovery_event(
    *,
    task_id: str | uuid.UUID,
    node_id: str | uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
    session: AsyncSession | None = None,
) -> None:
    node_key = str(node_id)
    if event_type not in {"chapter_preview", "review_score"}:
        return

    try:
        task_uuid = uuid.UUID(str(task_id))
    except (TypeError, ValueError, AttributeError):
        return

    if session is not None:
        task = await session.get(Task, task_uuid)
        if task is None:
            return
        _apply_monitor_recovery_event(
            task,
            node_id=node_key,
            event_type=event_type,
            payload=payload,
        )
        return

    async with async_session_factory() as inner_session:
        task = await inner_session.get(Task, task_uuid)
        if task is None:
            return
        _apply_monitor_recovery_event(
            task,
            node_id=node_key,
            event_type=event_type,
            payload=payload,
        )
        await inner_session.commit()


def task_visible_to_user(
    task: Task | Any,
    *,
    user_id: str,
    is_admin: bool,
) -> bool:
    if is_admin:
        return True
    owner_id = str(task.owner_id or "").strip()
    requested_user_id = user_id.strip()
    if not owner_id or not requested_user_id:
        return False
    return owner_id == requested_user_id


async def list_tasks(
    session: AsyncSession,
    *,
    user_id: str = "",
    offset: int = 0,
    limit: int = 50,
    status: str | None = None,
    mode: str | None = None,
    search: str | None = None,
) -> tuple[list[TaskRead], int]:
    """Return tasks ordered by creation time (newest first), with filters and total count."""
    from sqlalchemy import func, select as sa_select
    stmt = sa_select(Task).order_by(Task.created_at.desc())
    if user_id:
        stmt = stmt.where(Task.owner_id == user_id)
    if status:
        stmt = stmt.where(Task.status == status)
    if mode:
        stmt = stmt.where(Task.mode == mode)
    if search:
        stmt = stmt.where(Task.title.ilike(f"%{search}%"))
    count_stmt = sa_select(func.count()).select_from(stmt.subquery())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()
    result = await session.execute(stmt.offset(offset).limit(limit))
    tasks = result.scalars().all()
    return [TaskRead.model_validate(t) for t in tasks], total


async def batch_delete_tasks(
    session: AsyncSession,
    *,
    user_id: str,
    ids: list[uuid.UUID],
) -> int:
    """Delete tasks by id list scoped to user. Returns deleted count."""
    from sqlalchemy import delete
    if not ids:
        return 0
    stmt = delete(Task).where(Task.id.in_(ids))
    if user_id:
        stmt = stmt.where(Task.owner_id == user_id)
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount
