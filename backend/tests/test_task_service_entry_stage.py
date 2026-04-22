from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.schemas.task import TaskCreate
from app.services import task_service


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        now = datetime.now(UTC)
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                setattr(obj, "id", uuid.uuid4())
            if getattr(obj, "created_at", None) is None:
                setattr(obj, "created_at", now)
            if getattr(obj, "word_count", None) is None:
                setattr(obj, "word_count", 0)
            if hasattr(obj, "fsm_state") and getattr(obj, "fsm_state", None) is None:
                setattr(obj, "fsm_state", "init")
            if hasattr(obj, "retry_count") and getattr(obj, "retry_count", None) is None:
                setattr(obj, "retry_count", 0)

    async def commit(self) -> None:
        pass


class _DummyLLM:
    pass


@pytest.mark.asyncio
async def test_create_task_defaults_to_init_when_no_mid_entry(monkeypatch: pytest.MonkeyPatch):
    async def _fake_decompose_task(**_kwargs):
        return SimpleNamespace(
            nodes=[
                SimpleNamespace(id="n1", title="outline", role="outline", depends_on=[]),
            ]
        )

    monkeypatch.setattr(task_service, "decompose_task", _fake_decompose_task)

    session = _FakeSession()
    task_in = TaskCreate(title="A valid long task title for init path")

    detail = await task_service.create_task(session, task_in, _DummyLLM())
    assert detail.fsm_state == "init"


@pytest.mark.asyncio
async def test_create_task_uses_pre_review_integrity_for_draft_entry(
    monkeypatch: pytest.MonkeyPatch,
):
    async def _fake_decompose_task(**_kwargs):
        return SimpleNamespace(
            nodes=[
                SimpleNamespace(id="n1", title="outline", role="outline", depends_on=[]),
            ]
        )

    monkeypatch.setattr(task_service, "decompose_task", _fake_decompose_task)

    session = _FakeSession()
    task_in = TaskCreate(
        title="A valid long task title for mid entry",
        draft_text="existing draft",
    )

    detail = await task_service.create_task(session, task_in, _DummyLLM())
    assert detail.fsm_state == "pre_review_integrity"

    task_row = next(
        obj for obj in session.added
        if hasattr(obj, "checkpoint_data")
    )
    assert task_row.checkpoint_data["entry_stage"] == "pre_review_integrity"
    assert task_row.checkpoint_data["entry_inputs"]["has_draft_text"] is True
    assert task_row.checkpoint_data["routing_snapshot"]["required_roles"] == ["outline"]
