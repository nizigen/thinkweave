"""Task 管理路由 — /api/tasks"""

import uuid
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from typing import Optional

from app.schemas.task import (
    BatchDeleteRequest,
    BatchDeleteResult,
    DecompositionAuditRead,
    TaskControlAdminRetryRequest,
    TaskControlAdminSkipRequest,
    TaskControlForceTransitionRequest,
    TaskControlResumeFromCheckpointRequest,
    TaskControlRetryRequest,
    TaskControlSkipRequest,
    TaskCreate,
    TaskDetailRead,
    TaskListResult,
    TaskRead,
)
from app.security.auth import AuthContext, require_auth_context, require_user_id
from app.security.rate_limit import enforce_task_create_rate_limit
from app.services import task_control, task_service
from app.services.task_decomposer import TaskValidationError
from app.config import settings
from app.utils.llm_client import (
    BaseLLMClient,
    DebugMockLLMClient,
    LLMClient,
    LLMUnavailableError,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ---------------------------------------------------------------------------
# LLM client dependency — overridable in tests via app.dependency_overrides
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_llm_client() -> BaseLLMClient:
    """Return a LLM client instance. Override via app.dependency_overrides in tests."""
    if settings.mock_llm_enabled:
        return DebugMockLLMClient()
    return LLMClient()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=TaskListResult)
async def list_tasks(
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(require_user_id),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    status: Optional[str] = None,
    mode: Optional[str] = None,
    search: Optional[str] = None,
):
    """获取历史任务列表（分页 + 过滤）"""
    items, total = await task_service.list_tasks(
        session,
        user_id=user_id,
        offset=offset,
        limit=min(limit, 200),
        status=status,
        mode=mode,
        search=search,
    )
    return TaskListResult(items=items, total=total)


@router.delete("", response_model=BatchDeleteResult)
async def batch_delete_tasks(
    body: BatchDeleteRequest,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(require_user_id),
):
    """批量删除任务（仅删除属于当前用户的任务）"""
    deleted = await task_service.batch_delete_tasks(
        session,
        user_id=user_id,
        ids=body.ids,
    )
    return BatchDeleteResult(deleted_count=deleted)


@router.post("", response_model=TaskDetailRead, status_code=201)
async def create_task(
    task_in: TaskCreate,
    session: AsyncSession = Depends(get_session),
    llm_client: BaseLLMClient = Depends(get_llm_client),
    user_id: str = Depends(require_user_id),
):
    """创建新任务 — 触发LLM分解生成DAG节点"""
    await enforce_task_create_rate_limit(user_id)
    try:
        return await task_service.create_task(session, task_in, llm_client, owner_id=user_id)
    except TaskValidationError as e:
        raise HTTPException(status_code=422, detail=e.issues)
    except LLMUnavailableError as e:
        raise HTTPException(status_code=503, detail=f"LLM service unavailable: {e}")


@router.get("/{task_id}", response_model=TaskDetailRead)
async def get_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_auth_context),
):
    """获取任务详情（含DAG节点树）"""
    detail = await task_service.get_task_detail(
        session,
        task_id,
        user_id=auth.user_id,
        is_admin=auth.is_admin,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return detail


@router.get("/{task_id}/decomposition-audit", response_model=DecompositionAuditRead)
async def get_task_decomposition_audit(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_auth_context),
):
    detail = await task_service.get_task_decomposition_audit(
        session,
        task_id,
        user_id=auth.user_id,
        is_admin=auth.is_admin,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return detail


@router.post("/{task_id}/control/pause", response_model=TaskDetailRead)
async def pause_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_auth_context),
):
    try:
        return await task_control.pause_task(
            session,
            task_id,
            user_id=auth.user_id,
            is_admin=auth.is_admin,
        )
    except task_control.TaskControlNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
    except task_control.TaskControlError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/{task_id}/control/resume", response_model=TaskDetailRead)
async def resume_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_auth_context),
):
    try:
        return await task_control.resume_task(
            session,
            task_id,
            user_id=auth.user_id,
            is_admin=auth.is_admin,
        )
    except task_control.TaskControlNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
    except task_control.TaskControlError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/{task_id}/control/skip", response_model=TaskDetailRead)
async def skip_node(
    task_id: uuid.UUID,
    body: TaskControlSkipRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_auth_context),
):
    try:
        return await task_control.skip_node(
            session,
            task_id,
            node_id=body.node_id,
            user_id=auth.user_id,
            is_admin=auth.is_admin,
        )
    except task_control.TaskControlNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
    except task_control.TaskControlError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/{task_id}/control/retry", response_model=TaskDetailRead)
async def retry_node(
    task_id: uuid.UUID,
    body: TaskControlRetryRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_auth_context),
):
    try:
        return await task_control.retry_node(
            session,
            task_id,
            node_id=body.node_id,
            user_id=auth.user_id,
            is_admin=auth.is_admin,
        )
    except task_control.TaskControlNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
    except task_control.TaskControlError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/{task_id}/control/admin/force-transition", response_model=TaskDetailRead)
async def force_transition(
    task_id: uuid.UUID,
    body: TaskControlForceTransitionRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_auth_context),
):
    try:
        return await task_control.admin_force_transition(
            session,
            task_id,
            to_state=body.to_state,
            reason=body.reason,
            user_id=auth.user_id,
            is_admin=auth.is_admin,
        )
    except task_control.TaskControlNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
    except task_control.TaskControlError as exc:
        detail = str(exc)
        status_code = 403 if "admin privileges required" in detail else 409
        raise HTTPException(status_code=status_code, detail=detail)


@router.post("/{task_id}/control/admin/resume-from-checkpoint", response_model=TaskDetailRead)
async def resume_from_checkpoint(
    task_id: uuid.UUID,
    body: TaskControlResumeFromCheckpointRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_auth_context),
):
    try:
        return await task_control.admin_resume_from_checkpoint(
            session,
            task_id,
            reason=body.reason,
            user_id=auth.user_id,
            is_admin=auth.is_admin,
        )
    except task_control.TaskControlNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
    except task_control.TaskControlError as exc:
        detail = str(exc)
        status_code = 403 if "admin privileges required" in detail else 409
        raise HTTPException(status_code=status_code, detail=detail)


@router.post("/{task_id}/control/admin/skip", response_model=TaskDetailRead)
async def admin_skip_node(
    task_id: uuid.UUID,
    body: TaskControlAdminSkipRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_auth_context),
):
    try:
        return await task_control.admin_skip_node(
            session,
            task_id,
            node_id=body.node_id,
            reason=body.reason,
            user_id=auth.user_id,
            is_admin=auth.is_admin,
        )
    except task_control.TaskControlNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
    except task_control.TaskControlError as exc:
        detail = str(exc)
        status_code = 403 if "admin privileges required" in detail else 409
        raise HTTPException(status_code=status_code, detail=detail)


@router.post("/{task_id}/control/admin/retry", response_model=TaskDetailRead)
async def admin_retry(
    task_id: uuid.UUID,
    body: TaskControlAdminRetryRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(require_auth_context),
):
    try:
        return await task_control.admin_retry_node(
            session,
            task_id,
            node_id=body.node_id,
            reason=body.reason,
            user_id=auth.user_id,
            is_admin=auth.is_admin,
        )
    except task_control.TaskControlNotFoundError:
        raise HTTPException(status_code=404, detail="Task not found")
    except task_control.TaskControlError as exc:
        detail = str(exc)
        status_code = 403 if "admin privileges required" in detail else 409
        raise HTTPException(status_code=status_code, detail=detail)
