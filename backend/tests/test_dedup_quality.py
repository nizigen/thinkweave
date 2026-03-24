from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.services.dedup_quality import (
    compare_dedup_quality,
    compute_dedup_quality,
    evaluate_dedup_quality,
)


def test_compute_dedup_quality_detects_duplicate_pair() -> None:
    report = compute_dedup_quality(
        [
            {"node_id": "n1", "title": "A", "content": "量子 计算 原理 与 门模型"},
            {"node_id": "n2", "title": "B", "content": "量子 计算 原理 与 门模型"},
            {"node_id": "n3", "title": "C", "content": "供应链 优化 与 调度 策略"},
        ],
        threshold=0.85,
    )

    assert report["chapter_count"] == 3
    assert report["pair_count"] == 3
    assert report["duplicate_pairs"] == 1
    assert report["duplicate_rate"] == pytest.approx(1 / 3, rel=1e-5)
    assert any(pair["duplicate"] for pair in report["pairs"])


def test_compute_dedup_quality_handles_single_chapter() -> None:
    report = compute_dedup_quality(
        [{"node_id": "n1", "title": "A", "content": "only one chapter"}]
    )
    assert report["pair_count"] == 0
    assert report["duplicate_pairs"] == 0
    assert report["duplicate_rate"] == 0.0


def test_compute_dedup_quality_caps_text_length() -> None:
    repeated = ("alpha " * 2000).strip()
    report = compute_dedup_quality(
        [
            {"node_id": "n1", "title": "A", "content": repeated},
            {"node_id": "n2", "title": "B", "content": repeated},
        ],
        max_chars_per_chapter=64,
    )
    assert report["pair_count"] == 1
    assert report["duplicate_rate"] == 1.0


@pytest.mark.asyncio
async def test_evaluate_dedup_quality_reads_writer_nodes_only() -> None:
    class _FakeScalars:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return _FakeScalars(self._rows)

    class _FakeSession:
        def __init__(self, rows):
            self._rows = rows

        async def execute(self, stmt):
            stmt_text = str(stmt)
            assert "task_nodes.agent_role" in stmt_text
            assert "task_nodes.result IS NOT NULL" in stmt_text
            assert "ORDER BY task_nodes.title" in stmt_text
            assert "LIMIT" in stmt_text
            filtered = [
                row
                for row in self._rows
                if row.agent_role == "writer" and row.result is not None
            ]
            return _FakeResult(filtered)

    task_id = uuid.uuid4()
    session = _FakeSession(
        [
            SimpleNamespace(
                id=uuid.uuid4(),
                task_id=task_id,
                title="writer chapter 1",
                agent_role="writer",
                status="done",
                result="A B C D E F",
            ),
            SimpleNamespace(
                id=uuid.uuid4(),
                task_id=task_id,
                title="writer chapter 2",
                agent_role="writer",
                status="done",
                result="A B C D E F",
            ),
            SimpleNamespace(
                id=uuid.uuid4(),
                task_id=task_id,
                title="outline node",
                agent_role="outline",
                status="done",
                result="A B C D E F",
            ),
            SimpleNamespace(
                id=uuid.uuid4(),
                task_id=task_id,
                title="writer empty result",
                agent_role="writer",
                status="done",
                result=None,
            ),
        ]
    )

    report = await evaluate_dedup_quality(session=session, task_id=task_id)

    assert report["task_id"] == str(task_id)
    assert report["chapter_count"] == 2
    assert report["pair_count"] == 1
    assert report["duplicate_pairs"] == 1
    assert report["duplicate_rate"] == 1.0


@pytest.mark.asyncio
async def test_compare_dedup_quality_builds_delta_report() -> None:
    class _FakeTask:
        def __init__(self, owner_id: str) -> None:
            self.owner_id = owner_id

    class _FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

    class _FakeSession:
        def __init__(self) -> None:
            self._execute_count = 0

        async def get(self, model, key):
            return _FakeTask("test-user")

        async def execute(self, stmt):
            self._execute_count += 1
            if self._execute_count == 1:
                rows = [
                    SimpleNamespace(
                        id=uuid.uuid4(),
                        task_id=baseline_task_id,
                        title="writer chapter 1",
                        agent_role="writer",
                        status="done",
                        result="A B C",
                    ),
                    SimpleNamespace(
                        id=uuid.uuid4(),
                        task_id=baseline_task_id,
                        title="writer chapter 2",
                        agent_role="writer",
                        status="done",
                        result="A B C",
                    ),
                ]
            else:
                rows = [
                    SimpleNamespace(
                        id=uuid.uuid4(),
                        task_id=candidate_task_id,
                        title="writer chapter 1",
                        agent_role="writer",
                        status="done",
                        result="A B C",
                    ),
                    SimpleNamespace(
                        id=uuid.uuid4(),
                        task_id=candidate_task_id,
                        title="writer chapter 2",
                        agent_role="writer",
                        status="done",
                        result="X Y Z",
                    ),
                ]
            return _FakeResult(rows)

    baseline_task_id = uuid.uuid4()
    candidate_task_id = uuid.uuid4()
    report = await compare_dedup_quality(
        session=_FakeSession(),
        baseline_task_id=baseline_task_id,
        candidate_task_id=candidate_task_id,
        goal_threshold=0.05,
        user_id="test-user",
    )

    assert report["goal_threshold"] == 0.05
    assert report["goal_met"] is True
    assert report["duplicate_rate_delta"] >= 0.05
    assert report["baseline_report"]["task_id"] == str(baseline_task_id)
    assert report["candidate_report"]["task_id"] == str(candidate_task_id)
