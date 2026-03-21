"""Task service layer — create / read / list tasks + DAG persistence"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.task_node import TaskNode
from app.schemas.task import TaskCreate, TaskDetailRead, TaskNodeRead, TaskRead
from app.services.entry_stage import build_entry_metadata
from app.services.task_decomposer import decompose_task, TaskValidationError
from app.utils.llm_client import BaseLLMClient
from app.utils.logger import logger


async def create_task(
    session: AsyncSession,
    task_in: TaskCreate,
    llm_client: BaseLLMClient,
) -> TaskDetailRead:
    """
    Create a task, trigger LLM decomposition, persist DAG nodes.

    Flow: create Task row → decompose via LLM → create TaskNode rows → return detail.
    """
    # 1. 持久化 Task 主记录
    entry_meta = build_entry_metadata(
        draft_text=task_in.draft_text,
        review_comments=task_in.review_comments,
    )
    task = Task(
        title=task_in.title,
        mode=task_in.mode,
        depth=task_in.depth,
        target_words=task_in.target_words,
        status="decomposing",
        fsm_state=entry_meta["entry_stage"],
        checkpoint_data=entry_meta,
    )
    session.add(task)
    await session.flush()

    logger.bind(task_id=str(task.id), mode=task.mode).info(
        "Task created, starting decomposition"
    )

    # 2. 调用分解服务获取 DAG
    dag = await decompose_task(
        title=task_in.title,
        mode=task_in.mode,
        depth=task_in.depth,
        target_words=task_in.target_words,
        llm_client=llm_client,
    )

    # 3. DAG 节点 string ID → UUID 映射（数据库用 UUID 主键）
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

    # 4. 更新任务状态
    task.status = "pending"
    await session.flush()

    logger.bind(task_id=str(task.id), node_count=len(nodes)).info(
        "DAG nodes persisted"
    )

    # 5. 构建返回值
    node_reads = [
        TaskNodeRead(
            id=n.id,
            task_id=n.task_id,
            title=n.title,
            agent_role=n.agent_role,
            status=n.status,
            depends_on=n.depends_on,
            retry_count=n.retry_count,
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
        nodes=node_reads,
    )


async def get_task_detail(
    session: AsyncSession, task_id: uuid.UUID
) -> TaskDetailRead | None:
    """Get a task with its DAG nodes. Returns None if not found."""
    task = await session.get(Task, task_id)
    if task is None:
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
    task_read.nodes = node_reads
    return task_read


async def list_tasks(session: AsyncSession) -> list[TaskRead]:
    """Return all tasks ordered by creation time (newest first)."""
    result = await session.execute(
        select(Task).order_by(Task.created_at.desc())
    )
    tasks = result.scalars().all()
    return [TaskRead.model_validate(t) for t in tasks]
