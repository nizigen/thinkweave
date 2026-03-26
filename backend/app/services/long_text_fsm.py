"""Finite-state machine for long-text generation workflow."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Awaitable, Callable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import communicator
from app.memory.session import SessionMemory
from app.models.task import Task
from app.utils.logger import logger


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------

class LongTextState(str, Enum):
    """Long-text FSM states."""
    INIT = "init"
    OUTLINE = "outline"
    OUTLINE_REVIEW = "outline_review"
    WRITING = "writing"
    PRE_REVIEW_INTEGRITY = "pre_review_integrity"
    REVIEWING = "reviewing"
    RE_REVIEW = "re_review"
    RE_REVISE = "re_revise"
    CONSISTENCY = "consistency"
    FINAL_INTEGRITY = "final_integrity"
    DONE = "done"
    FAILED = "failed"


class CheckpointPolicy(str, Enum):
    """Checkpoint detail policy.

    FULL: include full workflow context (default).
    SLIM: include only minimal recoverability keys.
    MANDATORY: include required execution keys but omit heavy retry stats.
    """

    FULL = "full"
    SLIM = "slim"
    MANDATORY = "mandatory"


# ---------------------------------------------------------------------------
# Transition map
# ---------------------------------------------------------------------------

TRANSITIONS: dict[str, tuple[str, ...]] = {
    "init": ("outline", "failed"),
    "outline": ("outline_review", "failed"),
    "outline_review": ("writing", "failed"),
    "writing": ("pre_review_integrity", "failed"),
    "pre_review_integrity": ("reviewing", "re_revise", "failed"),
    "reviewing": ("re_review", "consistency", "failed"),
    "re_review": ("re_revise", "consistency", "failed"),
    "re_revise": ("re_review", "final_integrity", "failed"),
    "consistency": ("re_revise", "final_integrity", "failed"),
    "final_integrity": ("done", "re_revise", "failed"),
    "done": (),
    "failed": (),
}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_REVIEW_RETRIES = 3
MAX_CONSISTENCY_RETRIES = 2
REVIEW_PASS_THRESHOLD = 70


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class InvalidTransitionError(Exception):
    """Raised when an FSM transition is not allowed."""

    def __init__(self, current: LongTextState, target: LongTextState) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"Invalid FSM transition: {current.value} -> {target.value}"
        )


class TransitionGuardError(Exception):
    """Raised when a guarded transition requires explicit gate decision."""

    def __init__(self, current: LongTextState, target: LongTextState) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"Transition guard failed: {current.value} -> {target.value} requires gate_passed=True"
        )


# ---------------------------------------------------------------------------
# LongTextFSM
# ---------------------------------------------------------------------------

class LongTextFSM:
    """Finite-state machine controller for long-text generation tasks.

    This class owns state transition validation, checkpoint persistence,
    and crash recovery loading.
    """

    def __init__(
        self,
        task_id: uuid.UUID,
        state: LongTextState = LongTextState.INIT,
        checkpoint_policy: CheckpointPolicy = CheckpointPolicy.FULL,
        event_sender: Callable[..., Awaitable[Any]] | None = None,
    ) -> None:
        self.task_id = task_id
        self._state = state
        self._checkpoint_policy = checkpoint_policy
        self._event_sender = event_sender or communicator.send_task_event
        self._review_retry_counts: dict[int, int] = {}
        self._consistency_retry_count: int = 0
        self._completed_chapters: set[int] = set()
        self.session_memory_namespace: str = ""

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> LongTextState:
        return self._state

    @property
    def review_retry_counts(self) -> dict[int, int]:
        return dict(self._review_retry_counts)

    @property
    def consistency_retry_count(self) -> int:
        return self._consistency_retry_count

    @property
    def completed_chapters(self) -> set[int]:
        return set(self._completed_chapters)

    # ------------------------------------------------------------------
    # Transition validation
    # ------------------------------------------------------------------

    def can_transition(self, target: LongTextState) -> bool:
        """Check whether transitioning to *target* is allowed."""
        return target.value in TRANSITIONS.get(self._state.value, ())

    async def transition(
        self,
        target: LongTextState,
        *,
        session: AsyncSession,
        gate_passed: bool | None = None,
        commit: bool = True,
    ) -> None:
        """Validate and execute a state transition.

        Persists both ``fsm_state`` and ``checkpoint_data`` to the DB.
        Raises :class:`InvalidTransitionError` if the move is illegal.
        """
        if not self.can_transition(target):
            raise InvalidTransitionError(self._state, target)

        # Guardrails for mandatory quality gates.
        if (
            self._state is LongTextState.PRE_REVIEW_INTEGRITY
            and target is LongTextState.REVIEWING
            and gate_passed is not True
        ):
            raise TransitionGuardError(self._state, target)
        if (
            self._state is LongTextState.FINAL_INTEGRITY
            and target is LongTextState.DONE
            and gate_passed is not True
        ):
            raise TransitionGuardError(self._state, target)

        old = self._state
        self._state = target

        log = logger.bind(task_id=str(self.task_id))
        log.info("FSM transition: {} -> {}", old.value, target.value)

        # Persist state + checkpoint atomically (optimistic lock on old state)
        await self._persist_and_checkpoint(
            session,
            expected_old_state=old,
            commit=commit,
        )
        if self._event_sender is not None:
            try:
                await self._event_sender(
                    task_id=self.task_id,
                    msg_type="dag_update",
                    payload={
                        "from_state": old.value,
                        "to_state": target.value,
                    },
                )
            except Exception:
                log.opt(exception=True).warning("failed to emit dag_update event")

        if target in (LongTextState.DONE, LongTextState.FAILED):
            await self._cleanup_session_memory()

    # ------------------------------------------------------------------
    # Retry tracking
    # ------------------------------------------------------------------

    def increment_review_retry(self, chapter_index: int) -> None:
        """Increment the review retry counter for a chapter."""
        self._review_retry_counts[chapter_index] = (
            self._review_retry_counts.get(chapter_index, 0) + 1
        )

    def is_review_retry_exceeded(self, chapter_index: int) -> bool:
        return self._review_retry_counts.get(chapter_index, 0) >= MAX_REVIEW_RETRIES

    def increment_consistency_retry(self) -> None:
        self._consistency_retry_count += 1

    def is_consistency_retry_exceeded(self) -> bool:
        return self._consistency_retry_count >= MAX_CONSISTENCY_RETRIES

    # ------------------------------------------------------------------
    # Chapter tracking
    # ------------------------------------------------------------------

    def mark_chapter_completed(self, chapter_index: int) -> None:
        self._completed_chapters.add(chapter_index)

    def is_chapter_completed(self, chapter_index: int) -> bool:
        return chapter_index in self._completed_chapters

    # ------------------------------------------------------------------
    # Checkpoint
    # ------------------------------------------------------------------

    def get_checkpoint_data(self) -> dict[str, Any]:
        """Build a checkpoint dict (serialisable to JSONB)."""
        base = {
            "fsm_state": self._state.value,
            "checkpoint_policy": self._checkpoint_policy.value,
            "checkpoint_at": datetime.now(UTC).isoformat(),
            "session_memory_namespace": self.session_memory_namespace,
        }

        if self._checkpoint_policy is CheckpointPolicy.SLIM:
            return base

        if self._checkpoint_policy is CheckpointPolicy.MANDATORY:
            return {
                **base,
                "completed_chapters": sorted(self._completed_chapters),
            }

        return {
            **base,
            "completed_chapters": sorted(self._completed_chapters),
            "review_retry_count": {
                str(k): v for k, v in self._review_retry_counts.items()
            },
            "consistency_retry_count": self._consistency_retry_count,
        }

    async def checkpoint(
        self,
        *,
        session: AsyncSession,
        commit: bool = True,
    ) -> None:
        """Persist the current FSM snapshot to ``tasks.checkpoint_data``."""
        await self._persist_and_checkpoint(session, commit=commit)

    # ------------------------------------------------------------------
    # Resume (class method)
    # ------------------------------------------------------------------

    @classmethod
    async def resume(
        cls,
        task_id: uuid.UUID,
        *,
        session: AsyncSession,
    ) -> LongTextFSM:
        """Restore an FSM instance from the DB checkpoint.

        Raises ``ValueError`` if the task does not exist.
        """
        task = await session.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        state = LongTextState(task.fsm_state)
        fsm = cls(task_id=task_id, state=state)

        cp = task.checkpoint_data
        if cp:
            fsm._completed_chapters = set(cp.get("completed_chapters", []))
            fsm._review_retry_counts = {
                int(k): v
                for k, v in cp.get("review_retry_count", {}).items()
            }
            fsm._consistency_retry_count = cp.get("consistency_retry_count", 0)
            fsm.session_memory_namespace = cp.get("session_memory_namespace", "")

        log = logger.bind(task_id=str(task_id))
        log.info("FSM resumed at state={}", state.value)
        return fsm

    # ------------------------------------------------------------------
    # Internal - DB persistence
    # ------------------------------------------------------------------

    async def _persist_and_checkpoint(
        self,
        session: AsyncSession,
        expected_old_state: LongTextState | None = None,
        commit: bool = True,
    ) -> None:
        """Write ``fsm_state`` + ``checkpoint_data`` to the tasks row.

        When *expected_old_state* is given, an optimistic-lock WHERE clause
        ensures the row still has the expected state.  If another coroutine
        already changed it, ``rowcount == 0`` and we raise.
        """
        data = self.get_checkpoint_data()
        stmt = (
            update(Task)
            .where(Task.id == self.task_id)
            .values(
                fsm_state=self._state.value,
                checkpoint_data=data,
            )
        )
        if expected_old_state is not None:
            stmt = stmt.where(Task.fsm_state == expected_old_state.value)
        result = await session.execute(stmt)
        if result.rowcount == 0:
            if expected_old_state is not None:
                # Rollback in-memory state on concurrent modification
                self._state = expected_old_state
            raise ValueError(f"Task {self.task_id} not found or concurrently modified")
        if commit:
            await session.commit()
        else:
            await session.flush()

    async def initialize_session_memory(
        self,
        *,
        session: AsyncSession,
        commit: bool = True,
    ) -> str:
        """Initialize session memory and persist namespace to checkpoint_data.

        Call this when entering the OUTLINE state so crash recovery can
        re-attach to the correct memory namespace.
        """
        memory = SessionMemory(task_id=str(self.task_id))
        await memory.initialize()
        self.session_memory_namespace = memory.namespace

        stmt = (
            update(Task)
            .where(Task.id == self.task_id)
            .values(
                checkpoint_data={
                    **self.get_checkpoint_data(),
                    "session_memory_namespace": memory.namespace,
                }
            )
        )
        await session.execute(stmt)
        if commit:
            await session.commit()
        else:
            await session.flush()

        logger.bind(task_id=str(self.task_id)).info(
            "Session memory initialized: namespace={}", memory.namespace
        )
        return memory.namespace

    async def finalize_output(
        self,
        *,
        session: AsyncSession,
        commit: bool = True,
    ) -> int:
        """Assemble completed writer node results into tasks.output_text.

        Queries all writer nodes with non-None results, joins them in title
        order, updates tasks.output_text and tasks.word_count, and returns
        the word count.
        """
        from app.models.task_node import TaskNode  # avoid circular at module level

        result = await session.execute(
            select(TaskNode)
            .where(TaskNode.task_id == self.task_id)
            .where(TaskNode.agent_role == "writer")
            .where(TaskNode.result.is_not(None))
        )
        nodes = list(result.scalars().all())
        # Natural sort: split numeric tokens so "Chapter 10" sorts after "Chapter 9".
        def _natural_key(n: Any) -> list[Any]:
            return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", n.title or "")]
        nodes.sort(key=_natural_key)

        parts = [node.result for node in nodes if node.result]
        output_text = "\n\n".join(parts)
        word_count = len(re.findall(r'[\u4e00-\u9fff]', output_text)) + len(re.findall(r'[a-zA-Z]+', output_text)) if output_text else 0

        await session.execute(
            update(Task)
            .where(Task.id == self.task_id)
            .values(output_text=output_text or None, word_count=word_count)
        )
        if commit:
            await session.commit()
        else:
            await session.flush()

        logger.bind(task_id=str(self.task_id)).info(
            "Output finalized: {} chapters, {} words", len(nodes), word_count
        )
        return word_count

    async def _cleanup_session_memory(self) -> None:
        """Cleanup session-scoped memory when the task reaches terminal states."""
        try:
            memory = SessionMemory(task_id=str(self.task_id))
            await memory.initialize()
            await memory.cleanup()
        except Exception:
            logger.bind(task_id=str(self.task_id)).opt(exception=True).warning(
                "Session memory cleanup failed"
            )


# ---------------------------------------------------------------------------
# Service-restart recovery
# ---------------------------------------------------------------------------

async def scan_and_resume_running_tasks(
    *,
    session: AsyncSession,
) -> list[LongTextFSM]:
    """Find all tasks with ``status='running'`` and resume their FSMs.

    Called once at service startup to recover from crashes.
    """
    stmt = select(Task).where(Task.status == "running")
    result = await session.execute(stmt)
    running_tasks = list(result.scalars().all())

    fsms: list[LongTextFSM] = []
    for task in running_tasks:
        try:
            fsm = await LongTextFSM.resume(task_id=task.id, session=session)
            fsms.append(fsm)
            logger.info("Resumed FSM for task {}", task.id)
        except (ValueError, KeyError, TypeError):
            logger.opt(exception=True).error(
                "Failed to resume FSM for task {}", task.id
            )

    return fsms



