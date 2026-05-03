from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.task_node import TaskNode
from app.services.state_store import (
    ConcurrentModificationError,
    StateStore,
    StateTransitionConflictError,
)


async def _create_task(
    session: AsyncSession,
    *,
    fsm_state: str = "init",
) -> Task:
    task = Task(
        id=uuid.uuid4(),
        title="state-store-task",
        mode="report",
        status="running",
        fsm_state=fsm_state,
        target_words=10000,
        depth="standard",
        checkpoint_data={},
    )
    session.add(task)
    await session.flush()
    return task


async def _create_node(
    session: AsyncSession,
    *,
    task_id: uuid.UUID,
    status: str = "running",
) -> TaskNode:
    node = TaskNode(
        id=uuid.uuid4(),
        task_id=task_id,
        title="node-1",
        agent_role="writer",
        status=status,
        retry_count=0,
        version=0,
    )
    session.add(node)
    await session.flush()
    return node


@pytest.mark.asyncio
async def test_transition_fsm_appends_transition_log_and_event(db_session: AsyncSession):
    sender = AsyncMock()
    store = StateStore(event_sender=sender)
    task = await _create_task(db_session, fsm_state="init")

    await store.transition_fsm(
        session=db_session,
        task_id=task.id,
        from_state="init",
        to_state="outline",
        reason="unit-test",
        created_by="tester",
        metadata={"ticket": "P6-01"},
    )

    refreshed = await db_session.get(Task, task.id)
    assert refreshed is not None
    assert refreshed.fsm_state == "outline"
    cp = refreshed.checkpoint_data or {}
    logs = cp.get("transition_logs", [])
    assert isinstance(logs, list) and logs
    assert logs[-1]["from_state"] == "init"
    assert logs[-1]["to_state"] == "outline"
    assert logs[-1]["reason"] == "unit-test"
    sender.assert_awaited_once()


@pytest.mark.asyncio
async def test_transition_fsm_rejects_invalid_from_state(db_session: AsyncSession):
    store = StateStore(event_sender=AsyncMock())
    task = await _create_task(db_session, fsm_state="writing")

    with pytest.raises(StateTransitionConflictError):
        await store.transition_fsm(
            session=db_session,
            task_id=task.id,
            from_state="init",
            to_state="outline",
            reason="invalid",
        )


@pytest.mark.asyncio
async def test_update_node_status_optimistic_lock(db_session: AsyncSession):
    store = StateStore(event_sender=AsyncMock())
    task = await _create_task(db_session, fsm_state="writing")
    node = await _create_node(db_session, task_id=task.id, status="running")

    next_version = await store.update_node_status(
        session=db_session,
        node_id=node.id,
        expected_version=0,
        expected_status="running",
        values={"status": "done", "result": "ok"},
    )
    assert next_version == 1

    with pytest.raises(ConcurrentModificationError):
        await store.update_node_status(
            session=db_session,
            node_id=node.id,
            expected_version=0,
            expected_status="running",
            values={"status": "failed"},
        )
