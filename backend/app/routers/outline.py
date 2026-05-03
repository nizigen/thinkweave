"""大纲路由 — GET /api/tasks/{task_id}/outline, POST /api/tasks/{task_id}/outline/confirm"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.task import Outline, Task
from app.security.auth import require_user_id
from app.services.state_store import StateStore, StateTransitionConflictError

router = APIRouter(prefix="/api/tasks", tags=["outline"])


class OutlineRead(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    content: str
    version: int
    confirmed: bool

    model_config = {"from_attributes": True}


class OutlineConfirmRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=500_000)


async def _get_task_for_user(task_id: uuid.UUID, user_id: str, db: AsyncSession) -> Task:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.owner_id and task.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return task


@router.get("/{task_id}/outline", response_model=OutlineRead)
async def get_outline(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user_id: str = Depends(require_user_id),
):
    """获取任务当前大纲（最新版本）"""
    await _get_task_for_user(task_id, user_id, db)
    result = await db.execute(
        select(Outline)
        .where(Outline.task_id == task_id)
        .order_by(Outline.version.desc())
        .limit(1)
    )
    outline = result.scalar_one_or_none()
    if outline is None:
        raise HTTPException(status_code=404, detail="Outline not ready yet")
    return OutlineRead.model_validate(outline)


@router.post("/{task_id}/outline/confirm", response_model=OutlineRead)
async def confirm_outline(
    task_id: uuid.UUID,
    body: OutlineConfirmRequest,
    db: AsyncSession = Depends(get_session),
    user_id: str = Depends(require_user_id),
):
    """用户确认（或编辑后确认）大纲，推进 FSM 进入写作阶段"""
    task = await _get_task_for_user(task_id, user_id, db)
    if task.fsm_state != "outline_review":
        raise HTTPException(
            status_code=409,
            detail=f"Task is in state '{task.fsm_state}', cannot confirm outline now",
        )
    # 获取或创建大纲记录
    result = await db.execute(
        select(Outline)
        .where(Outline.task_id == task_id)
        .order_by(Outline.version.desc())
        .limit(1)
    )
    outline = result.scalar_one_or_none()
    if outline is None:
        outline = Outline(task_id=task_id, content=body.content, version=1, confirmed=True)
        db.add(outline)
    else:
        outline.content = body.content
        outline.confirmed = True
    # 推进 FSM 状态（统一走 StateStore 边界）
    store = StateStore()
    try:
        await store.transition_fsm(
            session=db,
            task_id=task_id,
            from_state="outline_review",
            to_state="writing",
            reason="outline_confirmed_by_user",
            created_by=user_id or "user",
            metadata={"outline_confirmed": True},
            checkpoint_data=task.checkpoint_data if isinstance(task.checkpoint_data, dict) else None,
        )
    except StateTransitionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.refresh(outline)
    return OutlineRead.model_validate(outline)
