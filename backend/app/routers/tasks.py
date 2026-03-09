"""Task 管理路由 — /api/tasks"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.task import TaskCreate, TaskDetailRead, TaskRead
from app.services import task_service
from app.services.task_decomposer import TaskValidationError
from app.utils.llm_client import BaseLLMClient, LLMClient

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ---------------------------------------------------------------------------
# LLM client dependency — overridable in tests via app.dependency_overrides
# ---------------------------------------------------------------------------

def get_llm_client() -> BaseLLMClient:
    """Return a LLM client instance. Override via app.dependency_overrides in tests."""
    return LLMClient()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=list[TaskRead])
async def list_tasks(session: AsyncSession = Depends(get_session)):
    """获取历史任务列表"""
    return await task_service.list_tasks(session)


@router.post("", response_model=TaskDetailRead, status_code=201)
async def create_task(
    task_in: TaskCreate,
    session: AsyncSession = Depends(get_session),
    llm_client: BaseLLMClient = Depends(get_llm_client),
):
    """创建新任务 — 触发LLM分解生成DAG节点"""
    try:
        return await task_service.create_task(session, task_in, llm_client)
    except TaskValidationError as e:
        raise HTTPException(status_code=422, detail=e.issues)


@router.get("/{task_id}", response_model=TaskDetailRead)
async def get_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """获取任务详情（含DAG节点树）"""
    detail = await task_service.get_task_detail(session, task_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return detail
