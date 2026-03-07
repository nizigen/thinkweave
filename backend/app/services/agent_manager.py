"""Agent CRUD service layer"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.schemas.agent import AgentCreate, AgentStatusUpdate


async def list_agents(session: AsyncSession) -> list[Agent]:
    """Return all agents ordered by creation time (newest first)."""
    result = await session.execute(select(Agent).order_by(Agent.created_at.desc()))
    return list(result.scalars().all())


async def get_agent(session: AsyncSession, agent_id: uuid.UUID) -> Agent | None:
    """Return a single agent by ID, or None."""
    return await session.get(Agent, agent_id)


async def create_agent(session: AsyncSession, agent_in: AgentCreate) -> Agent:
    """Register a new agent."""
    agent = Agent(**agent_in.model_dump())
    session.add(agent)
    await session.flush()
    await session.refresh(agent)
    return agent


async def update_agent_status(
    session: AsyncSession,
    agent_id: uuid.UUID,
    status_in: AgentStatusUpdate,
) -> Agent | None:
    """Update an agent's status. Returns None if agent not found."""
    agent = await session.get(Agent, agent_id)
    if agent is None:
        return None
    agent.status = status_in.status
    await session.flush()
    await session.refresh(agent)
    return agent


async def delete_agent(session: AsyncSession, agent_id: uuid.UUID) -> bool:
    """Delete an agent. Returns False if agent not found."""
    agent = await session.get(Agent, agent_id)
    if agent is None:
        return False
    await session.delete(agent)
    await session.flush()
    return True
