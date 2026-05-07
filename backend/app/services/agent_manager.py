"""Agent CRUD service layer"""

import copy
import time
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    available_model_options,
    resolve_model_choice,
    settings,
)
from app.models.agent import Agent
from app.schemas.agent import AgentCreate, AgentStatusUpdate
from app.services.runtime_bootstrap import (
    register_persisted_agent,
    unregister_runtime_agent,
)
from app.services.heartbeat import HEARTBEAT_TIMEOUT_SECONDS, get_agent_state
from app.skills.loader import SkillLoader
from app.utils.logger import logger


_ROLE_PRESET_CATALOG: dict[str, dict[str, object]] = {
    "orchestrator": {
        "layer": 0,
        "label": "编排 (Orchestrator)",
        "description": "任务分解与全局协调",
        "icon": "🎯",
        "skill_allowlist": ["model_selection_guard"],
    },
    "manager": {
        "layer": 1,
        "label": "管理 (Manager)",
        "description": "资源调度与策略管理",
        "icon": "📋",
        "skill_allowlist": ["model_selection_guard"],
    },
    "outline": {
        "layer": 2,
        "label": "大纲 (Outline)",
        "description": "结构规划与章节设计",
        "icon": "🗂️",
        "skill_allowlist": [
            "outline_claim_contract",
            "chapter_non_overlap",
            "technical_report",
            "no_hallucination_policy",
        ],
    },
    "writer": {
        "layer": 2,
        "label": "写作 (Writer)",
        "description": "内容撰写与创作",
        "icon": "✍️",
        "skill_allowlist": [
            "writer_evidence_first_policy",
            "revision_closure_policy",
            "research_tooling_policy",
            "experiment_analysis_protocol",
            "no_hallucination_policy",
            "evidence_driven_report",
            "quantified_claims",
            "chapter_non_overlap",
            "technical_report",
        ],
    },
    "researcher": {
        "layer": 2,
        "label": "调研 (Researcher)",
        "description": "证据检索计划与来源约束",
        "icon": "📚",
        "skill_allowlist": [
            "research_tooling_policy",
            "no_hallucination_policy",
            "evidence_driven_report",
            "quantified_claims",
            "technical_report",
        ],
    },
    "reviewer": {
        "layer": 2,
        "label": "审查 (Reviewer)",
        "description": "质量评分与反馈",
        "icon": "🔍",
        "skill_allowlist": [
            "reviewer_gate_policy",
            "reviewer_redline_logic_check",
            "reviewer_reject_bias_policy",
            "experiment_analysis_protocol",
            "no_hallucination_policy",
            "evidence_driven_report",
            "quantified_claims",
        ],
    },
    "consistency": {
        "layer": 2,
        "label": "一致性 (Consistency)",
        "description": "跨章节一致性检查",
        "icon": "🔗",
        "skill_allowlist": [
            "consistency_integrity_gate",
            "no_hallucination_policy",
        ],
    },
}

_ROLE_PRESET_ORDER = [
    "orchestrator",
    "manager",
    "outline",
    "researcher",
    "writer",
    "reviewer",
    "consistency",
]
_AUTO_APPLY_PRESET_ROLES = frozenset({"outline", "researcher", "writer", "reviewer", "consistency"})


def _normalize_capabilities(raw: str | None) -> str | None:
    if raw is None:
        return None
    normalized = raw.replace("\n", ",").replace(";", ",").replace("|", ",")
    seen: set[str] = set()
    out: list[str] = []
    for item in normalized.split(","):
        token = item.strip().lower()
        if not token:
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    if not out:
        return None
    return ", ".join(out)


def _normalize_preset_allowlist(
    candidates: list[str],
) -> list[str]:
    # Keep preset defaults stable even when runtime skill/tool discovery is incomplete.
    return list(candidates)


def _resolve_role_preset(role: str) -> dict[str, object] | None:
    raw = _ROLE_PRESET_CATALOG.get(role)
    if raw is None:
        return None

    preset = copy.deepcopy(raw)

    skill_allowlist = _normalize_preset_allowlist(
        list(preset.get("skill_allowlist", [])),
    )

    preset["agent_config"] = {
        "skill_allowlist": skill_allowlist,
    }
    preset["skill_allowlist"] = skill_allowlist
    return preset


def _build_default_agent_config(role: str) -> dict[str, object] | None:
    if role not in _AUTO_APPLY_PRESET_ROLES:
        return None
    preset = _resolve_role_preset(role)
    if preset is None:
        return None
    config = preset.get("agent_config")
    if not isinstance(config, dict):
        return None
    return copy.deepcopy(config)


async def list_agents(session: AsyncSession) -> list[Agent]:
    """Return all agents ordered by creation time (newest first)."""
    result = await session.execute(select(Agent).order_by(Agent.created_at.desc()))
    return list(result.scalars().all())


async def get_agent(session: AsyncSession, agent_id: uuid.UUID) -> Agent | None:
    """Return a single agent by ID, or None."""
    return await session.get(Agent, agent_id)


async def get_agent_health(
    session: AsyncSession,
    agent_id: uuid.UUID,
) -> dict[str, object] | None:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        return None

    state = await get_agent_state(agent_id)
    status = str(getattr(agent, "status", "") or "offline").strip().lower() or "offline"
    runtime_status = "offline" if status == "offline" else "dead"
    current_task = ""
    current_node = ""
    capabilities = str(getattr(agent, "capabilities", "") or "") or None
    error_count = 0
    last_heartbeat: float | None = None
    heartbeat_age_seconds: float | None = None

    if state:
        current_task = str(state.get("current_task", "") or "")
        current_node = str(state.get("current_node", "") or "")
        capabilities = str(state.get("capabilities", "") or capabilities or "") or None
        try:
            error_count = max(0, int(state.get("error_count", "0") or 0))
        except Exception:
            error_count = 0
        try:
            last_heartbeat = float(state.get("last_heartbeat", "0") or 0)
        except Exception:
            last_heartbeat = None
        if last_heartbeat and last_heartbeat > 0:
            heartbeat_age_seconds = max(0.0, time.time() - last_heartbeat)
            if heartbeat_age_seconds >= HEARTBEAT_TIMEOUT_SECONDS:
                runtime_status = "dead"
            else:
                runtime_status = str(state.get("status", "") or "unknown").strip().lower() or "unknown"
        else:
            runtime_status = "unknown"

        if error_count > 0 and runtime_status in {"idle", "busy"}:
            runtime_status = "degraded"

    return {
        "id": agent.id,
        "status": status,
        "runtime_status": runtime_status,
        "current_task": current_task,
        "current_node": current_node,
        "capabilities": capabilities,
        "error_count": error_count,
        "last_heartbeat": last_heartbeat,
        "heartbeat_age_seconds": heartbeat_age_seconds,
    }


async def create_agent(session: AsyncSession, agent_in: AgentCreate) -> Agent:
    """Register a new agent."""
    payload = agent_in.model_dump()
    payload["capabilities"] = _normalize_capabilities(payload.get("capabilities"))
    if payload.get("agent_config") is None:
        default_config = _build_default_agent_config(str(payload.get("role", "")))
        if default_config is not None:
            payload["agent_config"] = default_config
    payload["model"] = resolve_model_choice(
        payload.get("model"),
        payload.get("custom_model"),
        settings.default_model,
    )
    payload.pop("custom_model", None)
    agent = Agent(**payload)
    session.add(agent)
    await session.flush()
    await session.commit()
    await session.refresh(agent)
    try:
        await register_persisted_agent(agent)
    except Exception:
        agent.status = "offline"
        await session.flush()
        await session.commit()
        await session.refresh(agent)
        logger.bind(agent_id=str(agent.id), agent_role=agent.role).opt(
            exception=True
        ).warning("runtime registration failed; agent persisted as offline")
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
    await session.commit()
    await unregister_runtime_agent(agent_id)
    return True


def list_agent_model_options() -> list[dict[str, str]]:
    return available_model_options([settings.default_model])


def list_agent_role_presets() -> list[dict[str, object]]:
    presets: list[dict[str, object]] = []
    for role in _ROLE_PRESET_ORDER:
        preset = _resolve_role_preset(role)
        if preset is None:
            continue
        presets.append(
            {
                "role": role,
                "layer": int(preset.get("layer", 2)),
                "label": str(preset.get("label", role)),
                "description": str(preset.get("description", "")),
                "icon": str(preset.get("icon", "")),
                "default_model": settings.default_model,
                "agent_config": copy.deepcopy(
                    preset.get(
                        "agent_config",
                        {
                            "skill_allowlist": [],
                        },
                    )
                ),
            }
        )
    return presets


def list_agent_skill_options() -> list[dict[str, object]]:
    loader = SkillLoader()
    loader.load_all()
    options: list[dict[str, object]] = []
    for skill in loader.skills.values():
        options.append(
            {
                "name": skill.name,
                "skill_type": skill.skill_type.value,
                "description": skill.description,
                "applicable_roles": list(skill.applicable_roles),
                "applicable_modes": list(skill.applicable_modes),
                "applicable_stages": list(skill.applicable_stages),
                "tools": list(skill.tools),
                "model_preference": skill.model_preference,
                "priority": skill.priority,
                "source_path": skill.source_path,
            }
        )
    options.sort(key=lambda item: (int(item["priority"]), str(item["name"])))
    return options


