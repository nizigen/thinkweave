from __future__ import annotations

import uuid

import pytest

from app.models.task import Task
from app.models.task_decomposition_audit import TaskDecompositionAudit
from app.services.task_service import (
    _build_decomposition_audit_summary,
    _persist_decomposition_audit,
)


def test_build_decomposition_audit_summary_counts_fields():
    summary = _build_decomposition_audit_summary(
        {
            "decomposer_version": "v-test",
            "normalized_dag": {"nodes": [{"id": "n1"}, {"id": "n2"}]},
            "repair_actions": [{"step": "a"}],
            "validation_issues": ["bad role"],
        },
        attempt_no=3,
    )
    assert summary["attempt_no"] == 3
    assert summary["decomposer_version"] == "v-test"
    assert summary["node_count"] == 2
    assert summary["repair_actions_count"] == 1
    assert summary["validation_issues_count"] == 1


@pytest.mark.asyncio
async def test_persist_decomposition_audit_increments_attempt_no(db_session):
    task = Task(
        id=uuid.uuid4(),
        title="Audit test task",
        mode="report",
        status="pending",
        fsm_state="init",
        depth="standard",
        target_words=10000,
        checkpoint_data={},
    )
    db_session.add(task)
    await db_session.flush()

    first = await _persist_decomposition_audit(
        db_session,
        task_id=task.id,
        trace={
            "decomposition_input": {"title": "t1"},
            "raw_llm_output": {"nodes": []},
            "normalized_dag": {"nodes": [{"id": "n1"}]},
            "validation_issues": [],
            "repair_actions": [],
            "decomposer_version": "v-test",
        },
    )
    second = await _persist_decomposition_audit(
        db_session,
        task_id=task.id,
        trace={
            "decomposition_input": {"title": "t1b"},
            "raw_llm_output": {"nodes": [{"id": "x"}]},
            "normalized_dag": {"nodes": [{"id": "n1"}, {"id": "n2"}]},
            "validation_issues": ["fallback"],
            "repair_actions": [{"step": "fallback"}],
            "decomposer_version": "v-test",
        },
    )
    await db_session.flush()

    assert first == 1
    assert second == 2

    rows = (
        await db_session.execute(
            TaskDecompositionAudit.__table__.select().where(
                TaskDecompositionAudit.task_id == task.id
            )
        )
    ).fetchall()
    assert len(rows) == 2
