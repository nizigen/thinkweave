"""Runtime bootstrap for persisted agent rows.

This module bridges DB agent definitions with runtime worker instances.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from app.agents.agent_registry import agent_registry
from app.agents.consistency_agent import ConsistencyAgent
from app.agents.manager import ManagerAgent
from app.agents.orchestrator import OrchestratorAgent
from app.agents.outline_agent import OutlineAgent
from app.agents.researcher_agent import ResearcherAgent
from app.agents.reviewer_agent import ReviewerAgent
from app.agents.worker import WorkerAgent
from app.agents.writer_agent import WriterAgent
from app.config import settings
from app.database import async_session_factory
from app.models.agent import Agent
from app.models.task import Task
from app.services.dag_scheduler import start_scheduler
from app.services.heartbeat import wait_for_agent_healthy
from app.utils.logger import logger
from app.utils.llm_client import DebugMockLLMClient, LLMClient

_runtime_mcp_client: Any | None = None
_runtime_llm_client: Any | None = None


async def _ensure_required_role_agents(session: Any) -> int:
    """Ensure critical roles exist before runtime registration."""
    created = 0
    result = await session.execute(select(Agent.role))
    existing_roles = {str(row[0] or "").strip().lower() for row in result.all()}

    if "researcher" not in existing_roles:
        agent = Agent(
            name="researcher-auto",
            role="researcher",
            layer=2,
            capabilities="research, retrieval, evidence, source_policy",
            model=settings.default_model,
            status="idle",
        )
        session.add(agent)
        created += 1

    if created:
        await session.flush()
    return created


def set_runtime_mcp_client(client: Any | None) -> None:
    """Register runtime MCP client instance for option introspection."""
    global _runtime_mcp_client
    _runtime_mcp_client = client


def get_runtime_mcp_client() -> Any | None:
    """Return runtime MCP client if bootstrap has provided one."""
    return _runtime_mcp_client


def _get_runtime_llm_client() -> Any:
    global _runtime_llm_client
    if _runtime_llm_client is None:
        _runtime_llm_client = (
            DebugMockLLMClient() if settings.mock_llm_enabled else LLMClient()
        )
    return _runtime_llm_client


def _build_runtime_agent(agent: Agent) -> Any:
    role = str(getattr(agent, "role", "") or "").strip().lower()
    common = {
        "agent_id": agent.id,
        "name": str(agent.name or role or "agent"),
        "llm_client": _get_runtime_llm_client(),
        "capabilities": str(getattr(agent, "capabilities", "") or ""),
    }
    if role == "orchestrator":
        return OrchestratorAgent(**common)
    if role == "manager":
        return ManagerAgent(**common)
    if role == "outline":
        return OutlineAgent(**common)
    if role == "researcher":
        return ResearcherAgent(**common)
    if role == "writer":
        return WriterAgent(**common)
    if role == "reviewer":
        return ReviewerAgent(**common)
    if role == "consistency":
        return ConsistencyAgent(**common)
    return WorkerAgent(role=role or "writer", layer=int(getattr(agent, "layer", 2) or 2), **common)


async def register_persisted_agent(agent: Any) -> None:
    """Register one persisted agent row into runtime and start its loop."""
    agent_id = getattr(agent, "id", None)
    if agent_id is None:
        return
    runtime_agent = _build_runtime_agent(agent)
    agent_registry.register(runtime_agent)
    await agent_registry.start_agent(agent_id)
    healthy = await wait_for_agent_healthy(agent_id, timeout_seconds=5.0, poll_interval=0.2)
    if not healthy:
        await agent_registry.stop_agent(agent_id)
        agent_registry.unregister(agent_id)
        raise RuntimeError(f"agent startup health check timeout: {agent_id}")
    logger.bind(agent_id=str(agent_id), role=str(getattr(agent, "role", ""))).info(
        "runtime agent registered and started"
    )


async def unregister_runtime_agent(agent_id: Any) -> None:
    """Unregister one runtime agent."""
    try:
        await agent_registry.stop_agent(agent_id)
    finally:
        agent_registry.unregister(agent_id)
    logger.bind(agent_id=str(agent_id)).info("runtime agent unregistered")


async def bootstrap_runtime_agents() -> int:
    """Load persisted agents from DB and start runtime loops."""
    started = 0
    async with async_session_factory() as session:
        created = await _ensure_required_role_agents(session)
        if created:
            await session.commit()
            logger.info("auto-created missing role agents: {}", created)

        result = await session.execute(select(Agent))
        agents = list(result.scalars().all())
        for agent in agents:
            try:
                await register_persisted_agent(agent)
                agent.status = "idle"
                started += 1
            except Exception:
                agent.status = "offline"
                logger.bind(agent_id=str(agent.id), role=agent.role).opt(
                    exception=True
                ).warning("runtime bootstrap failed for agent")
        await session.commit()
    logger.info("runtime bootstrap complete: started={}", started)
    return started


async def bootstrap_active_task_schedulers() -> int:
    """Resume schedulers for active tasks after process restart."""
    if not settings.bootstrap_resume_tasks:
        logger.info("task scheduler bootstrap skipped by config")
        return 0

    limit = int(getattr(settings, "bootstrap_resume_task_limit", 0) or 0)
    started = 0
    async with async_session_factory() as session:
        total_result = await session.execute(
            select(func.count()).select_from(Task).where(Task.status.in_(("pending", "running")))
        )
        total_candidates = int(total_result.scalar_one() or 0)

        query = (
            select(Task.id, Task.status, Task.checkpoint_data)
            .where(Task.status.in_(("pending", "running")))
            .order_by(Task.created_at.desc())
        )
        if limit > 0:
            query = query.limit(limit)
        result = await session.execute(
            query
        )
        rows = list(result.all())

    skipped = max(0, total_candidates - len(rows))
    if skipped > 0:
        logger.warning(
            "task scheduler bootstrap capped: resumed_latest={} skipped_old={}",
            len(rows),
            skipped,
        )

    for task_id, _status, checkpoint_data in rows:
        control = {}
        if isinstance(checkpoint_data, dict):
            maybe_control = checkpoint_data.get("control")
            if isinstance(maybe_control, dict):
                control = maybe_control
        control_status = str(control.get("status", "active") or "active").lower()
        if control_status in {"paused", "pause_requested"}:
            continue
        try:
            await start_scheduler(task_id)
            started += 1
        except Exception:
            logger.bind(task_id=str(task_id)).opt(exception=True).warning(
                "failed to resume scheduler during bootstrap"
            )

    logger.info("task scheduler bootstrap complete: started={}", started)
    return started


async def shutdown_runtime_agents() -> None:
    """Stop all runtime agent loops."""
    try:
        await agent_registry.stop_all()
    finally:
        for agent in list(agent_registry.list_all()):
            agent_registry.unregister(agent.agent_id)
    logger.info("runtime agents stopped")
