"""Tests for long_text_fsm.py (long-text FSM).

TDD RED phase: all tests written before implementation.
Organized by component:
  1. State enum + transition validation (pure logic, no DB)
  2. FSM core (init, transition, retry counting)
  3. Checkpoint persistence (needs DB)
  4. Resume from checkpoint (needs DB)
  5. Service restart recovery (needs DB)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.task_node import TaskNode
from app.services.long_text_fsm import (
    CheckpointPolicy,
    TRANSITIONS,
    InvalidTransitionError,
    LongTextFSM,
    LongTextState,
    MAX_CONSISTENCY_RETRIES,
    MAX_REVIEW_RETRIES,
    REVIEW_PASS_THRESHOLD,
    TransitionGuardError,
    scan_and_resume_running_tasks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_task(
    session: AsyncSession,
    *,
    fsm_state: str = "init",
    status: str = "pending",
    checkpoint_data: dict | None = None,
) -> Task:
    """Insert a Task row for testing."""
    task = Task(
        id=uuid.uuid4(),
        title="Test long text task",
        mode="report",
        status=status,
        fsm_state=fsm_state,
        depth="standard",
        target_words=10000,
        checkpoint_data=checkpoint_data,
    )
    session.add(task)
    await session.flush()
    return task


# ===========================================================================
# 1. State enum + transition map
# ===========================================================================

class TestLongTextState:
    """LongTextState enum values match the spec."""

    def test_all_states_defined(self):
        expected = {
            "init",
            "outline",
            "outline_review",
            "writing",
            "pre_review_integrity",
            "reviewing",
            "re_review",
            "re_revise",
            "consistency",
            "final_integrity",
            "done",
            "failed",
        }
        actual = {s.value for s in LongTextState}
        assert actual == expected

    def test_state_from_string(self):
        assert LongTextState("init") is LongTextState.INIT
        assert LongTextState("writing") is LongTextState.WRITING

    def test_invalid_state_raises(self):
        with pytest.raises(ValueError):
            LongTextState("nonexistent")


class TestTransitionMap:
    """TRANSITIONS dict defines valid state transitions per spec."""

    def test_init_can_go_to_outline(self):
        assert "outline" in TRANSITIONS["init"]

    def test_outline_can_go_to_outline_review(self):
        assert "outline_review" in TRANSITIONS["outline"]

    def test_outline_review_can_go_to_writing(self):
        assert "writing" in TRANSITIONS["outline_review"]

    def test_writing_can_go_to_reviewing(self):
        assert "pre_review_integrity" in TRANSITIONS["writing"]

    def test_pre_review_integrity_can_go_to_reviewing_or_re_revise(self):
        targets = TRANSITIONS["pre_review_integrity"]
        assert "reviewing" in targets
        assert "re_revise" in targets

    def test_reviewing_can_go_to_re_review_or_consistency(self):
        targets = TRANSITIONS["reviewing"]
        assert "re_review" in targets
        assert "consistency" in targets

    def test_consistency_can_go_to_re_revise_or_final_integrity(self):
        targets = TRANSITIONS["consistency"]
        assert "re_revise" in targets
        assert "final_integrity" in targets

    def test_final_integrity_can_go_to_done_or_re_revise(self):
        targets = TRANSITIONS["final_integrity"]
        assert "done" in targets
        assert "re_revise" in targets

    def test_done_is_terminal(self):
        assert len(TRANSITIONS["done"]) == 0

    def test_failed_is_terminal(self):
        assert len(TRANSITIONS["failed"]) == 0

    def test_all_states_have_transition_entry(self):
        for state in LongTextState:
            assert state.value in TRANSITIONS

    def test_any_state_can_go_to_failed(self):
        """Non-terminal states should be able to transition to failed."""
        non_terminal = {
            "init",
            "outline",
            "outline_review",
            "writing",
            "pre_review_integrity",
            "reviewing",
            "re_review",
            "re_revise",
            "consistency",
            "final_integrity",
        }
        for state_val in non_terminal:
            assert "failed" in TRANSITIONS[state_val], (
                f"{state_val} should allow transition to failed"
            )


class TestConstants:
    """FSM constants match BACKEND_STRUCTURE.md spec."""

    def test_max_review_retries(self):
        assert MAX_REVIEW_RETRIES == 3

    def test_max_consistency_retries(self):
        assert MAX_CONSISTENCY_RETRIES == 2

    def test_review_pass_threshold(self):
        assert REVIEW_PASS_THRESHOLD == 70


class TestCheckpointPolicy:
    def test_checkpoint_policy_values(self):
        assert CheckpointPolicy.FULL.value == "full"
        assert CheckpointPolicy.SLIM.value == "slim"
        assert CheckpointPolicy.MANDATORY.value == "mandatory"

    def test_full_policy_contains_all_fields(self):
        fsm = LongTextFSM(task_id=uuid.uuid4(), checkpoint_policy=CheckpointPolicy.FULL)
        fsm.mark_chapter_completed(1)
        fsm.increment_review_retry(1)
        fsm.increment_consistency_retry()
        cp = fsm.get_checkpoint_data()
        assert cp["checkpoint_policy"] == "full"
        assert "completed_chapters" in cp
        assert "review_retry_count" in cp
        assert "consistency_retry_count" in cp

    def test_slim_policy_contains_minimum_fields(self):
        fsm = LongTextFSM(task_id=uuid.uuid4(), checkpoint_policy=CheckpointPolicy.SLIM)
        fsm.mark_chapter_completed(2)
        cp = fsm.get_checkpoint_data()
        assert cp["checkpoint_policy"] == "slim"
        assert "fsm_state" in cp
        assert "checkpoint_at" in cp
        assert "completed_chapters" not in cp
        assert "review_retry_count" not in cp
        assert "consistency_retry_count" not in cp

    def test_mandatory_policy_excludes_heavy_fields(self):
        fsm = LongTextFSM(
            task_id=uuid.uuid4(),
            checkpoint_policy=CheckpointPolicy.MANDATORY,
        )
        fsm.mark_chapter_completed(3)
        fsm.increment_review_retry(3)
        cp = fsm.get_checkpoint_data()
        assert cp["checkpoint_policy"] == "mandatory"
        assert "fsm_state" in cp
        assert "completed_chapters" in cp
        assert "review_retry_count" not in cp
        assert "consistency_retry_count" not in cp


# ===========================================================================
# 2. FSM core - init, transition, retry counting
# ===========================================================================

class TestFSMInit:
    """LongTextFSM initialization."""

    def test_default_state_is_init(self):
        fsm = LongTextFSM(task_id=uuid.uuid4())
        assert fsm.state is LongTextState.INIT

    def test_custom_initial_state(self):
        fsm = LongTextFSM(task_id=uuid.uuid4(), state=LongTextState.WRITING)
        assert fsm.state is LongTextState.WRITING

    def test_task_id_stored(self):
        tid = uuid.uuid4()
        fsm = LongTextFSM(task_id=tid)
        assert fsm.task_id == tid

    def test_retry_counts_start_at_zero(self):
        fsm = LongTextFSM(task_id=uuid.uuid4())
        assert fsm.review_retry_counts == {}
        assert fsm.consistency_retry_count == 0

    def test_completed_chapters_start_empty(self):
        fsm = LongTextFSM(task_id=uuid.uuid4())
        assert fsm.completed_chapters == set()


class TestFSMTransitionValidation:
    """can_transition() validates against the transition map."""

    def test_valid_transition_returns_true(self):
        fsm = LongTextFSM(task_id=uuid.uuid4())
        assert fsm.can_transition(LongTextState.OUTLINE) is True

    def test_invalid_transition_returns_false(self):
        fsm = LongTextFSM(task_id=uuid.uuid4())
        assert fsm.can_transition(LongTextState.DONE) is False

    def test_self_transition_not_allowed(self):
        fsm = LongTextFSM(task_id=uuid.uuid4())
        assert fsm.can_transition(LongTextState.INIT) is False

    def test_terminal_state_cannot_transition(self):
        fsm = LongTextFSM(task_id=uuid.uuid4(), state=LongTextState.DONE)
        for target in LongTextState:
            assert fsm.can_transition(target) is False

    def test_failed_state_cannot_transition(self):
        fsm = LongTextFSM(task_id=uuid.uuid4(), state=LongTextState.FAILED)
        for target in LongTextState:
            assert fsm.can_transition(target) is False


class TestFSMTransitionExecution:
    """transition() updates state and raises on invalid transitions."""

    @pytest.mark.asyncio
    async def test_valid_transition_updates_state(self, db_session):
        task = await _create_task(db_session)
        fsm = LongTextFSM(task_id=task.id)
        await fsm.transition(LongTextState.OUTLINE, session=db_session)
        assert fsm.state is LongTextState.OUTLINE

    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self, db_session):
        task = await _create_task(db_session)
        fsm = LongTextFSM(task_id=task.id)
        with pytest.raises(InvalidTransitionError):
            await fsm.transition(LongTextState.DONE, session=db_session)

    @pytest.mark.asyncio
    async def test_transition_persists_fsm_state_to_db(self, db_session):
        task = await _create_task(db_session)
        fsm = LongTextFSM(task_id=task.id)
        await fsm.transition(LongTextState.OUTLINE, session=db_session)

        refreshed = await db_session.get(Task, task.id)
        assert refreshed.fsm_state == "outline"

    @pytest.mark.asyncio
    async def test_transition_emits_dag_update_when_sender_provided(self):
        sender = AsyncMock()
        session = AsyncMock()
        fsm = LongTextFSM(task_id=uuid.uuid4(), event_sender=sender)

        await fsm.transition(LongTextState.OUTLINE, session=session)

        assert sender.await_count == 2
        first = sender.await_args_list[0].kwargs
        second = sender.await_args_list[1].kwargs
        assert first["msg_type"] == "state_event"
        assert first["payload"]["from_state"] == "init"
        assert first["payload"]["to_state"] == "outline"
        assert second["msg_type"] == "dag_update"
        assert second["payload"]["from_state"] == "init"
        assert second["payload"]["to_state"] == "outline"

    @pytest.mark.asyncio
    async def test_sequential_transitions(self, db_session):
        task = await _create_task(db_session)
        fsm = LongTextFSM(task_id=task.id)
        await fsm.transition(LongTextState.OUTLINE, session=db_session)
        await fsm.transition(LongTextState.OUTLINE_REVIEW, session=db_session)
        await fsm.transition(LongTextState.WRITING, session=db_session)
        await fsm.transition(LongTextState.PRE_REVIEW_INTEGRITY, session=db_session)
        await fsm.transition(
            LongTextState.REVIEWING, session=db_session, gate_passed=True
        )
        await fsm.transition(LongTextState.CONSISTENCY, session=db_session)
        await fsm.transition(LongTextState.FINAL_INTEGRITY, session=db_session)
        await fsm.transition(
            LongTextState.DONE, session=db_session, gate_passed=True
        )
        assert fsm.state is LongTextState.DONE


class TestFinalizeOutputAssembly:
    @pytest.mark.asyncio
    async def test_finalize_output_orders_by_chapter_and_skips_non_chapter_nodes(
        self,
        db_session: AsyncSession,
    ):
        task = await _create_task(db_session)
        db_session.add_all(
            [
                TaskNode(
                    task_id=task.id,
                    title="自动补写轮次1：全稿扩写与篇幅补足（目标补写约1200字）",
                    agent_role="writer",
                    status="done",
                    result='{"chapter_title":"全稿扩写","content_markdown":"[TIMEOUT_FALLBACK]","paragraphs":[{"text":"[TIMEOUT_FALLBACK]","citation_keys":[]}]}',
                ),
                TaskNode(
                    task_id=task.id,
                    title="第2章：方法与执行",
                    agent_role="writer",
                    status="done",
                    result='{"chapter_title":"第2章：方法与执行","content_markdown":"第二章正文说明执行方法。","paragraphs":[{"text":"第二章正文说明执行方法。","citation_keys":[]}]}',
                ),
                TaskNode(
                    task_id=task.id,
                    title="第1章：问题定义",
                    agent_role="writer",
                    status="done",
                    result='{"chapter_title":"第1章：问题定义","content_markdown":"第一章正文定义问题边界。","paragraphs":[{"text":"第一章正文定义问题边界。","citation_keys":[]}]}',
                ),
            ]
        )
        await db_session.flush()

        fsm = LongTextFSM(task_id=task.id)
        word_count = await fsm.finalize_output(session=db_session)

        await db_session.refresh(task)
        text = str(task.output_text or "")
        assert "## 第1章：问题定义" in text
        assert "## 第2章：方法与执行" in text
        assert text.index("## 第1章：问题定义") < text.index("## 第2章：方法与执行")
        assert "[TIMEOUT_FALLBACK]" not in text
        assert word_count > 0

    def test_count_words_excludes_markdown_and_json_scaffold(self):
        text = """# 标题

## 第1章：测试

{"chapter_title":"第1章","content_markdown":"ignored"}

这是正文内容 alpha beta。
"""
        count = LongTextFSM._count_words(text)
        assert count >= 8
        assert count < 20

    @pytest.mark.asyncio
    async def test_transition_to_failed_from_any_non_terminal(self, db_session):
        non_terminal = [
            LongTextState.INIT, LongTextState.OUTLINE,
            LongTextState.OUTLINE_REVIEW, LongTextState.WRITING,
            LongTextState.PRE_REVIEW_INTEGRITY, LongTextState.REVIEWING,
            LongTextState.RE_REVIEW, LongTextState.RE_REVISE,
            LongTextState.CONSISTENCY, LongTextState.FINAL_INTEGRITY,
        ]
        for start_state in non_terminal:
            task = await _create_task(db_session, fsm_state=start_state.value)
            fsm = LongTextFSM(task_id=task.id, state=start_state)
            await fsm.transition(LongTextState.FAILED, session=db_session)
            assert fsm.state is LongTextState.FAILED

    @pytest.mark.asyncio
    async def test_terminal_done_triggers_session_memory_cleanup(self, db_session):
        task = await _create_task(db_session, fsm_state="final_integrity")
        fsm = LongTextFSM(task_id=task.id, state=LongTextState.FINAL_INTEGRITY)
        fsm._cleanup_session_memory = AsyncMock()  # type: ignore[attr-defined]

        await fsm.transition(
            LongTextState.DONE, session=db_session, gate_passed=True
        )

        fsm._cleanup_session_memory.assert_awaited_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_terminal_failed_triggers_session_memory_cleanup(self, db_session):
        task = await _create_task(db_session, fsm_state="init")
        fsm = LongTextFSM(task_id=task.id, state=LongTextState.INIT)
        fsm._cleanup_session_memory = AsyncMock()  # type: ignore[attr-defined]

        await fsm.transition(LongTextState.FAILED, session=db_session)

        fsm._cleanup_session_memory.assert_awaited_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_non_terminal_transition_does_not_cleanup_session_memory(self, db_session):
        task = await _create_task(db_session, fsm_state="init")
        fsm = LongTextFSM(task_id=task.id, state=LongTextState.INIT)
        fsm._cleanup_session_memory = AsyncMock()  # type: ignore[attr-defined]

        await fsm.transition(LongTextState.OUTLINE, session=db_session)

        fsm._cleanup_session_memory.assert_not_awaited()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_guard_blocks_pre_review_to_reviewing_without_pass(self, db_session):
        task = await _create_task(db_session, fsm_state="pre_review_integrity")
        fsm = LongTextFSM(task_id=task.id, state=LongTextState.PRE_REVIEW_INTEGRITY)
        with pytest.raises(TransitionGuardError):
            await fsm.transition(LongTextState.REVIEWING, session=db_session)

    @pytest.mark.asyncio
    async def test_guard_blocks_final_integrity_to_done_without_pass(self, db_session):
        task = await _create_task(db_session, fsm_state="final_integrity")
        fsm = LongTextFSM(task_id=task.id, state=LongTextState.FINAL_INTEGRITY)
        with pytest.raises(TransitionGuardError):
            await fsm.transition(LongTextState.DONE, session=db_session)


class TestFSMRetryTracking:
    """Review and consistency retry counting."""

    def test_increment_review_retry(self):
        fsm = LongTextFSM(task_id=uuid.uuid4(), state=LongTextState.REVIEWING)
        fsm.increment_review_retry(chapter_index=0)
        assert fsm.review_retry_counts[0] == 1

    def test_increment_review_retry_multiple(self):
        fsm = LongTextFSM(task_id=uuid.uuid4(), state=LongTextState.REVIEWING)
        fsm.increment_review_retry(chapter_index=2)
        fsm.increment_review_retry(chapter_index=2)
        assert fsm.review_retry_counts[2] == 2

    def test_review_retry_exceeded(self):
        fsm = LongTextFSM(task_id=uuid.uuid4(), state=LongTextState.REVIEWING)
        for _ in range(MAX_REVIEW_RETRIES):
            fsm.increment_review_retry(chapter_index=1)
        assert fsm.is_review_retry_exceeded(chapter_index=1) is True

    def test_review_retry_not_exceeded(self):
        fsm = LongTextFSM(task_id=uuid.uuid4(), state=LongTextState.REVIEWING)
        fsm.increment_review_retry(chapter_index=1)
        assert fsm.is_review_retry_exceeded(chapter_index=1) is False

    def test_increment_consistency_retry(self):
        fsm = LongTextFSM(task_id=uuid.uuid4(), state=LongTextState.CONSISTENCY)
        fsm.increment_consistency_retry()
        assert fsm.consistency_retry_count == 1

    def test_consistency_retry_exceeded(self):
        fsm = LongTextFSM(task_id=uuid.uuid4(), state=LongTextState.CONSISTENCY)
        for _ in range(MAX_CONSISTENCY_RETRIES):
            fsm.increment_consistency_retry()
        assert fsm.is_consistency_retry_exceeded() is True

    def test_consistency_retry_not_exceeded(self):
        fsm = LongTextFSM(task_id=uuid.uuid4(), state=LongTextState.CONSISTENCY)
        fsm.increment_consistency_retry()
        assert fsm.is_consistency_retry_exceeded() is False

    def test_mark_chapter_completed(self):
        fsm = LongTextFSM(task_id=uuid.uuid4())
        fsm.mark_chapter_completed(0)
        fsm.mark_chapter_completed(2)
        assert fsm.completed_chapters == {0, 2}

    def test_is_chapter_completed(self):
        fsm = LongTextFSM(task_id=uuid.uuid4())
        fsm.mark_chapter_completed(1)
        assert fsm.is_chapter_completed(1) is True
        assert fsm.is_chapter_completed(0) is False


# ===========================================================================
# 3. Checkpoint persistence
# ===========================================================================

class TestCheckpoint:
    """checkpoint() saves FSM state to tasks.checkpoint_data JSONB."""

    @pytest.mark.asyncio
    async def test_checkpoint_writes_to_db(self, db_session):
        task = await _create_task(db_session)
        fsm = LongTextFSM(task_id=task.id)
        await fsm.transition(LongTextState.OUTLINE, session=db_session)

        refreshed = await db_session.get(Task, task.id)
        assert refreshed.checkpoint_data is not None
        assert refreshed.checkpoint_data["fsm_state"] == "outline"

    @pytest.mark.asyncio
    async def test_checkpoint_data_structure(self, db_session):
        task = await _create_task(db_session)
        fsm = LongTextFSM(task_id=task.id, state=LongTextState.REVIEWING)
        fsm.mark_chapter_completed(0)
        fsm.mark_chapter_completed(1)
        fsm.increment_review_retry(chapter_index=2)
        await fsm.checkpoint(session=db_session)

        refreshed = await db_session.get(Task, task.id)
        cp = refreshed.checkpoint_data
        assert cp["fsm_state"] == "reviewing"
        assert set(cp["completed_chapters"]) == {0, 1}
        assert cp["review_retry_count"]["2"] == 1
        assert cp["consistency_retry_count"] == 0
        assert "checkpoint_at" in cp

    @pytest.mark.asyncio
    async def test_checkpoint_auto_on_transition(self, db_session):
        """Every transition automatically saves a checkpoint."""
        task = await _create_task(db_session)
        fsm = LongTextFSM(task_id=task.id)
        await fsm.transition(LongTextState.OUTLINE, session=db_session)

        refreshed = await db_session.get(Task, task.id)
        assert refreshed.checkpoint_data is not None
        assert refreshed.checkpoint_data["fsm_state"] == "outline"

    @pytest.mark.asyncio
    async def test_checkpoint_preserves_retry_counts(self, db_session):
        task = await _create_task(db_session, fsm_state="reviewing")
        fsm = LongTextFSM(task_id=task.id, state=LongTextState.REVIEWING)
        fsm.increment_review_retry(chapter_index=0)
        fsm.increment_review_retry(chapter_index=0)
        fsm.increment_consistency_retry()
        await fsm.checkpoint(session=db_session)

        refreshed = await db_session.get(Task, task.id)
        cp = refreshed.checkpoint_data
        assert cp["review_retry_count"]["0"] == 2
        assert cp["consistency_retry_count"] == 1

    @pytest.mark.asyncio
    async def test_get_checkpoint_data_immutable(self):
        """get_checkpoint_data() returns a fresh dict each call."""
        fsm = LongTextFSM(task_id=uuid.uuid4())
        data1 = fsm.get_checkpoint_data()
        data2 = fsm.get_checkpoint_data()
        assert data1 is not data2
        # Exclude timestamp which may differ between rapid calls
        data1.pop("checkpoint_at")
        data2.pop("checkpoint_at")
        assert data1 == data2


# ===========================================================================
# 4. Resume from checkpoint
# ===========================================================================

class TestResume:
    """resume() restores FSM from tasks.checkpoint_data."""

    @pytest.mark.asyncio
    async def test_resume_restores_state(self, db_session):
        task = await _create_task(
            db_session,
            fsm_state="writing",
            status="running",
            checkpoint_data={
                "fsm_state": "writing",
                "completed_chapters": [0, 1],
                "review_retry_count": {},
                "consistency_retry_count": 0,
                "checkpoint_at": "2026-03-07T12:00:00",
            },
        )

        fsm = await LongTextFSM.resume(task_id=task.id, session=db_session)
        assert fsm.state is LongTextState.WRITING
        assert fsm.task_id == task.id

    @pytest.mark.asyncio
    async def test_resume_restores_completed_chapters(self, db_session):
        task = await _create_task(
            db_session,
            fsm_state="reviewing",
            status="running",
            checkpoint_data={
                "fsm_state": "reviewing",
                "completed_chapters": [0, 2, 3],
                "review_retry_count": {"1": 2},
                "consistency_retry_count": 0,
                "checkpoint_at": "2026-03-07T12:00:00",
            },
        )

        fsm = await LongTextFSM.resume(task_id=task.id, session=db_session)
        assert fsm.completed_chapters == {0, 2, 3}

    @pytest.mark.asyncio
    async def test_resume_restores_review_retry_counts(self, db_session):
        task = await _create_task(
            db_session,
            fsm_state="reviewing",
            status="running",
            checkpoint_data={
                "fsm_state": "reviewing",
                "completed_chapters": [],
                "review_retry_count": {"1": 2, "4": 1},
                "consistency_retry_count": 0,
                "checkpoint_at": "2026-03-07T12:00:00",
            },
        )

        fsm = await LongTextFSM.resume(task_id=task.id, session=db_session)
        assert fsm.review_retry_counts == {1: 2, 4: 1}

    @pytest.mark.asyncio
    async def test_resume_restores_consistency_retry_count(self, db_session):
        task = await _create_task(
            db_session,
            fsm_state="consistency",
            status="running",
            checkpoint_data={
                "fsm_state": "consistency",
                "completed_chapters": [0, 1, 2],
                "review_retry_count": {},
                "consistency_retry_count": 1,
                "checkpoint_at": "2026-03-07T12:00:00",
            },
        )

        fsm = await LongTextFSM.resume(task_id=task.id, session=db_session)
        assert fsm.consistency_retry_count == 1

    @pytest.mark.asyncio
    async def test_resume_restores_checkpoint_policy(self, db_session):
        task = await _create_task(
            db_session,
            fsm_state="consistency",
            status="running",
            checkpoint_data={
                "fsm_state": "consistency",
                "checkpoint_policy": "mandatory",
                "completed_chapters": [0],
                "review_retry_count": {"0": 1},
                "consistency_retry_count": 1,
            },
        )

        fsm = await LongTextFSM.resume(task_id=task.id, session=db_session)
        cp = fsm.get_checkpoint_data()
        assert cp["checkpoint_policy"] == "mandatory"

    @pytest.mark.asyncio
    async def test_resume_without_checkpoint_data(self, db_session):
        """Resume a task that has no checkpoint and use fsm_state from the DB."""
        task = await _create_task(
            db_session,
            fsm_state="outline",
            status="running",
            checkpoint_data=None,
        )

        fsm = await LongTextFSM.resume(task_id=task.id, session=db_session)
        assert fsm.state is LongTextState.OUTLINE
        assert fsm.completed_chapters == set()
        assert fsm.review_retry_counts == {}

    @pytest.mark.asyncio
    async def test_resume_nonexistent_task_raises(self, db_session):
        fake_id = uuid.uuid4()
        with pytest.raises(ValueError, match="not found"):
            await LongTextFSM.resume(task_id=fake_id, session=db_session)

    @pytest.mark.asyncio
    async def test_resume_does_not_reset_retry_counts(self, db_session):
        """Critical: crash recovery must not reset retry counters."""
        task = await _create_task(
            db_session,
            fsm_state="reviewing",
            status="running",
            checkpoint_data={
                "fsm_state": "reviewing",
                "completed_chapters": [0],
                "review_retry_count": {"1": 2},
                "consistency_retry_count": 1,
                "checkpoint_at": "2026-03-07T12:00:00",
            },
        )

        fsm = await LongTextFSM.resume(task_id=task.id, session=db_session)
        # Retry counts must be preserved, not reset
        assert fsm.review_retry_counts[1] == 2
        assert fsm.consistency_retry_count == 1


# ===========================================================================
# 5. Service restart recovery
# ===========================================================================

class TestScanAndResume:
    """scan_and_resume_running_tasks() finds and resumes running tasks."""

    @pytest_asyncio.fixture(autouse=True)
    async def clean_running_tasks(self, db_session):
        """Clear any running tasks left by previous tests before each scan test."""
        from sqlalchemy import text
        await db_session.execute(text("UPDATE tasks SET status='failed' WHERE status='running'"))
        await db_session.commit()
        yield

    @pytest.mark.asyncio
    async def test_scan_finds_running_tasks(self, db_session):
        await _create_task(db_session, fsm_state="writing", status="running",
                           checkpoint_data={"fsm_state": "writing",
                                            "completed_chapters": [],
                                            "review_retry_count": {},
                                            "consistency_retry_count": 0,
                                            "checkpoint_at": "2026-03-07T12:00:00"})
        await _create_task(db_session, fsm_state="done", status="done")
        await _create_task(db_session, fsm_state="init", status="pending")

        fsms = await scan_and_resume_running_tasks(session=db_session)
        assert len(fsms) == 1
        assert fsms[0].state is LongTextState.WRITING

    @pytest.mark.asyncio
    async def test_scan_returns_empty_when_none_running(self, db_session):
        await _create_task(db_session, fsm_state="done", status="done")

        fsms = await scan_and_resume_running_tasks(session=db_session)
        assert fsms == []

    @pytest.mark.asyncio
    async def test_scan_resumes_multiple_tasks(self, db_session):
        await _create_task(db_session, fsm_state="writing", status="running",
                           checkpoint_data={"fsm_state": "writing",
                                            "completed_chapters": [],
                                            "review_retry_count": {},
                                            "consistency_retry_count": 0,
                                            "checkpoint_at": "2026-03-07T12:00:00"})
        await _create_task(db_session, fsm_state="reviewing", status="running",
                           checkpoint_data={"fsm_state": "reviewing",
                                            "completed_chapters": [0],
                                            "review_retry_count": {"1": 1},
                                            "consistency_retry_count": 0,
                                            "checkpoint_at": "2026-03-07T12:00:00"})

        fsms = await scan_and_resume_running_tasks(session=db_session)
        assert len(fsms) == 2
        states = {f.state for f in fsms}
        assert LongTextState.WRITING in states
        assert LongTextState.REVIEWING in states

    @pytest.mark.asyncio
    async def test_scan_skips_task_with_corrupted_checkpoint(self, db_session):
        """Tasks with invalid fsm_state in DB should be skipped, not crash."""
        await _create_task(db_session, fsm_state="BOGUS", status="running",
                           checkpoint_data={"fsm_state": "BOGUS"})
        fsms = await scan_and_resume_running_tasks(session=db_session)
        assert len(fsms) == 0



# ===========================================================================
# 8. finalize_output — chapter assembly + output_text/word_count update
# ===========================================================================

class TestFinalizeOutput:
    """LongTextFSM.finalize_output() assembles writer nodes into output_text."""

    @pytest.mark.asyncio
    async def test_finalize_output_concatenates_writer_results(self, db_session):
        """Writer node results are joined and stored in tasks.output_text."""
        from app.models.task_node import TaskNode

        task = await _create_task(db_session, fsm_state="done")
        # Add two writer nodes with results
        n1 = TaskNode(
            id=uuid.uuid4(),
            task_id=task.id,
            title="Chapter 1",
            agent_role="writer",
            status="completed",
            result="Content of chapter one.",
        )
        n2 = TaskNode(
            id=uuid.uuid4(),
            task_id=task.id,
            title="Chapter 2",
            agent_role="writer",
            status="completed",
            result="Content of chapter two.",
        )
        db_session.add(n1)
        db_session.add(n2)
        await db_session.flush()

        fsm = LongTextFSM(task_id=task.id, state=LongTextState.DONE)
        word_count = await fsm.finalize_output(session=db_session)

        await db_session.refresh(task)
        assert task.output_text is not None
        assert "Content of chapter one." in task.output_text
        assert "Content of chapter two." in task.output_text
        assert task.word_count > 0
        assert word_count == task.word_count

    @pytest.mark.asyncio
    async def test_finalize_output_returns_zero_when_no_writers(self, db_session):
        """Returns 0 word_count when no writer nodes exist."""
        task = await _create_task(db_session, fsm_state="done")
        fsm = LongTextFSM(task_id=task.id, state=LongTextState.DONE)
        word_count = await fsm.finalize_output(session=db_session)
        assert word_count == 0

    @pytest.mark.asyncio
    async def test_finalize_output_skips_nodes_without_result(self, db_session):
        """Nodes with None result are skipped in assembly."""
        from app.models.task_node import TaskNode

        task = await _create_task(db_session, fsm_state="done")
        n1 = TaskNode(
            id=uuid.uuid4(),
            task_id=task.id,
            title="Chapter 1",
            agent_role="writer",
            status="completed",
            result="Real content here.",
        )
        n2 = TaskNode(
            id=uuid.uuid4(),
            task_id=task.id,
            title="Chapter 2",
            agent_role="writer",
            status="pending",
            result=None,
        )
        db_session.add(n1)
        db_session.add(n2)
        await db_session.flush()

        fsm = LongTextFSM(task_id=task.id, state=LongTextState.DONE)
        word_count = await fsm.finalize_output(session=db_session)

        await db_session.refresh(task)
        assert "Real content here." in (task.output_text or "")
        assert task.word_count == word_count

    @pytest.mark.asyncio
    async def test_finalize_output_prefers_assembly_editor_result(self, db_session):
        from app.models.task_node import TaskNode

        task = await _create_task(db_session, fsm_state="done")
        n1 = TaskNode(
            id=uuid.uuid4(),
            task_id=task.id,
            title="Chapter 1",
            agent_role="writer",
            status="completed",
            result="Draft chapter one content.",
        )
        n2 = TaskNode(
            id=uuid.uuid4(),
            task_id=task.id,
            title="全稿Assembly编辑收敛（术语统一/重复折叠/结论收敛）",
            agent_role="writer",
            status="completed",
            result="Final assembled manuscript with expanded consolidated details.",
        )
        db_session.add(n1)
        db_session.add(n2)
        await db_session.flush()

        fsm = LongTextFSM(task_id=task.id, state=LongTextState.DONE)
        await fsm.finalize_output(session=db_session)

        await db_session.refresh(task)
        assert task.output_text == "Final assembled manuscript with expanded consolidated details."

    @pytest.mark.asyncio
    async def test_finalize_output_keeps_base_when_assembly_too_short(self, db_session):
        from app.models.task_node import TaskNode

        task = await _create_task(db_session, fsm_state="done")
        n1 = TaskNode(
            id=uuid.uuid4(),
            task_id=task.id,
            title="Chapter 1",
            agent_role="writer",
            status="completed",
            result="This is chapter one with substantial detail and evidence.",
        )
        n2 = TaskNode(
            id=uuid.uuid4(),
            task_id=task.id,
            title="Chapter 2",
            agent_role="writer",
            status="completed",
            result="This is chapter two with substantial detail and analysis.",
        )
        n3 = TaskNode(
            id=uuid.uuid4(),
            task_id=task.id,
            title="全稿Assembly编辑收敛（术语统一/重复折叠/结论收敛）",
            agent_role="writer",
            status="completed",
            result="Too short.",
        )
        db_session.add(n1)
        db_session.add(n2)
        db_session.add(n3)
        await db_session.flush()

        fsm = LongTextFSM(task_id=task.id, state=LongTextState.DONE)
        await fsm.finalize_output(session=db_session)

        await db_session.refresh(task)
        assert "chapter one" in (task.output_text or "").lower()
        assert "chapter two" in (task.output_text or "").lower()


# ===========================================================================
# 9. session_memory_namespace in checkpoint
# ===========================================================================

class TestSessionMemoryNamespaceInCheckpoint:
    """session_memory_namespace is persisted in checkpoint_data."""

    @pytest.mark.asyncio
    async def test_initialize_session_memory_writes_namespace_to_checkpoint(
        self, db_session
    ):
        """After initialize_session_memory(), checkpoint includes namespace key."""
        task = await _create_task(db_session, fsm_state="outline")
        fsm = LongTextFSM(task_id=task.id, state=LongTextState.OUTLINE)
        await fsm.initialize_session_memory(session=db_session)

        await db_session.refresh(task)
        cp = task.checkpoint_data or {}
        assert "session_memory_namespace" in cp
        assert str(task.id) in cp["session_memory_namespace"]

    @pytest.mark.asyncio
    async def test_resume_restores_session_memory_namespace(self, db_session):
        """resume() populates session_memory_namespace from checkpoint_data."""
        task = await _create_task(
            db_session,
            fsm_state="writing",
            checkpoint_data={
                "fsm_state": "writing",
                "session_memory_namespace": "mem:test-123",
                "completed_chapters": [0],
                "review_retry_count": {},
                "consistency_retry_count": 0,
                "checkpoint_at": "2026-03-20T10:00:00",
            },
        )
        fsm = await LongTextFSM.resume(task_id=task.id, session=db_session)
        assert fsm.session_memory_namespace == "mem:test-123"
