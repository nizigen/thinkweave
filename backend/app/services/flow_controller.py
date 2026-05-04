"""Coordination boundary between node execution and FSM progression."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.services.state_store import StateStore, StateTransitionConflictError

FSM_STAGE_ORDER: dict[str, int] = {
    "init": 0,
    "outline": 1,
    "outline_review": 2,
    "premise_gate": 3,
    "writing": 4,
    "pre_review_integrity": 5,
    "reviewing": 6,
    "re_review": 7,
    "re_revise": 8,
    "consistency": 9,
    "final_integrity": 10,
    "done": 11,
    "failed": 11,
}

ROLE_TO_FSM_STAGE: dict[str, str] = {
    "outline": "outline",
    "researcher": "outline_review",
    "writer": "writing",
    "reviewer": "reviewing",
    "consistency": "consistency",
}


class FlowController:
    """Owns runtime flow decisions between FSM states and DAG execution roles."""

    def __init__(self, *, state_store: StateStore | None = None) -> None:
        self._state_store = state_store or StateStore()

    async def on_node_completed(
        self,
        *,
        session: AsyncSession,
        task_id: uuid.UUID,
        node_role: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        role = str(node_role or "").strip().lower()
        target_stage = ROLE_TO_FSM_STAGE.get(role)
        if not target_stage:
            return False

        task = await session.get(Task, task_id)
        if task is None:
            return False

        current = str(getattr(task, "fsm_state", "") or "init").strip().lower()
        if current == "outline_review" and target_stage == "writing":
            # Enforce premise gate before any path can reach writing.
            target_stage = "premise_gate"
        current_order = FSM_STAGE_ORDER.get(current, 0)
        target_order = FSM_STAGE_ORDER.get(target_stage, 0)
        if target_order <= current_order:
            return False

        checkpoint_data = (
            dict(task.checkpoint_data)
            if isinstance(task.checkpoint_data, dict)
            else {}
        )
        try:
            await self._state_store.transition_fsm(
                session=session,
                task_id=task_id,
                from_state=current,
                to_state=target_stage,
                reason="flow_controller_node_completed",
                created_by="flow_controller",
                metadata={
                    "node_role": role,
                    **(metadata or {}),
                },
                checkpoint_data=checkpoint_data,
                commit=False,
            )
        except StateTransitionConflictError:
            return False
        return True
