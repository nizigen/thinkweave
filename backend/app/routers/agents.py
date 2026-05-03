"""Agent management routes (/api/agents)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas.agent import (
    AgentCreate,
    AgentHealthRead,
    AgentRead,
    AgentStatusUpdate,
    ModelOptionRead,
    RolePresetRead,
    SkillOptionRead,
    ToolOptionRead,
)
from app.security.auth import require_admin_user_id
from app.services import agent_manager

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("", response_model=list[AgentRead])
async def list_agents(
    session: AsyncSession = Depends(get_session),
    _user_id: str = Depends(require_admin_user_id),
):
    return await agent_manager.list_agents(session)


@router.post("", response_model=AgentRead, status_code=201)
async def create_agent(
    agent_in: AgentCreate,
    session: AsyncSession = Depends(get_session),
    _user_id: str = Depends(require_admin_user_id),
):
    return await agent_manager.create_agent(session, agent_in)


@router.get("/model-options", response_model=list[ModelOptionRead])
async def list_agent_model_options(
    _user_id: str = Depends(require_admin_user_id),
):
    return agent_manager.list_agent_model_options()


@router.get("/role-presets", response_model=list[RolePresetRead])
async def list_agent_role_presets(
    _user_id: str = Depends(require_admin_user_id),
):
    return agent_manager.list_agent_role_presets()


@router.get("/skills", response_model=list[SkillOptionRead])
async def list_agent_skill_options(
    _user_id: str = Depends(require_admin_user_id),
):
    return agent_manager.list_agent_skill_options()


@router.get("/tool-options", response_model=list[ToolOptionRead])
async def list_agent_tool_options(
    _user_id: str = Depends(require_admin_user_id),
):
    return agent_manager.list_agent_tool_options()


@router.get("/{agent_id}", response_model=AgentRead)
async def get_agent(
    agent_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user_id: str = Depends(require_admin_user_id),
):
    agent = await agent_manager.get_agent(session, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.get("/{agent_id}/health", response_model=AgentHealthRead)
async def get_agent_health(
    agent_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user_id: str = Depends(require_admin_user_id),
):
    detail = await agent_manager.get_agent_health(session, agent_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return detail


@router.patch("/{agent_id}/status", response_model=AgentRead)
async def update_agent_status(
    agent_id: uuid.UUID,
    status_in: AgentStatusUpdate,
    session: AsyncSession = Depends(get_session),
    _user_id: str = Depends(require_admin_user_id),
):
    agent = await agent_manager.update_agent_status(session, agent_id, status_in)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user_id: str = Depends(require_admin_user_id),
):
    deleted = await agent_manager.delete_agent(session, agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Agent not found")
