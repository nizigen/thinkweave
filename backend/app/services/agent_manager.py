"""Agent CRUD service layer"""

import copy
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
    get_runtime_mcp_client,
    register_persisted_agent,
    unregister_runtime_agent,
)
from app.skills.loader import SkillLoader
from app.utils.logger import logger


_ROLE_PRESET_CATALOG: dict[str, dict[str, object]] = {
    "orchestrator": {
        "layer": 0,
        "label": "编排 (Orchestrator)",
        "description": "任务分解与全局协调",
        "icon": "🎯",
        "max_tool_iterations": 1,
        "skill_allowlist": ["model_selection_guard"],
        "tool_allowlist": ["sequentialthinking"],
    },
    "manager": {
        "layer": 1,
        "label": "管理 (Manager)",
        "description": "资源调度与策略管理",
        "icon": "📋",
        "max_tool_iterations": 1,
        "skill_allowlist": ["model_selection_guard"],
        "tool_allowlist": ["sequentialthinking"],
    },
    "outline": {
        "layer": 2,
        "label": "大纲 (Outline)",
        "description": "结构规划与章节设计",
        "icon": "🗂️",
        "max_tool_iterations": 2,
        "skill_allowlist": [
            "outline_claim_contract",
            "chapter_non_overlap",
            "technical_report",
            "no_hallucination_policy",
        ],
        "tool_allowlist": [
            "search_files",
            "read_text_file",
            "read_multiple_files",
            "tavily_search",
            "search_repositories",
        ],
    },
    "writer": {
        "layer": 2,
        "label": "写作 (Writer)",
        "description": "内容撰写与创作",
        "icon": "✍️",
        "max_tool_iterations": 3,
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
        "tool_allowlist": [
            "search_files",
            "read_text_file",
            "read_multiple_files",
            "tavily_search",
            "tavily_extract",
            "search_code",
            "get_file_contents",
        ],
    },
    "reviewer": {
        "layer": 2,
        "label": "审查 (Reviewer)",
        "description": "质量评分与反馈",
        "icon": "🔍",
        "max_tool_iterations": 2,
        "skill_allowlist": [
            "reviewer_gate_policy",
            "reviewer_redline_logic_check",
            "reviewer_reject_bias_policy",
            "experiment_analysis_protocol",
            "no_hallucination_policy",
            "evidence_driven_report",
            "quantified_claims",
        ],
        "tool_allowlist": [
            "search_files",
            "read_text_file",
            "read_multiple_files",
            "tavily_search",
            "search_code",
            "search_issues",
        ],
    },
    "consistency": {
        "layer": 2,
        "label": "一致性 (Consistency)",
        "description": "跨章节一致性检查",
        "icon": "🔗",
        "max_tool_iterations": 2,
        "skill_allowlist": [
            "consistency_integrity_gate",
            "no_hallucination_policy",
        ],
        "tool_allowlist": [
            "search_files",
            "read_text_file",
            "read_multiple_files",
        ],
    },
}

_ROLE_PRESET_ORDER = [
    "orchestrator",
    "manager",
    "outline",
    "writer",
    "reviewer",
    "consistency",
]
_AUTO_APPLY_PRESET_ROLES = frozenset({"outline", "writer", "reviewer", "consistency"})


def _normalize_preset_allowlist(
    candidates: list[str],
    available: set[str],
) -> list[str]:
    # Keep preset defaults stable even when runtime skill/tool discovery is incomplete.
    return list(candidates)


def _get_available_skill_names() -> set[str]:
    loader = SkillLoader()
    loader.load_all()
    return set(loader.skills.keys())


def _get_available_tool_names() -> set[str]:
    client = get_runtime_mcp_client()
    if client is None:
        return set()
    return {tool.name for tool in client.registry.list_tools()}


def _resolve_role_preset(role: str) -> dict[str, object] | None:
    return _resolve_role_preset_with_available(
        role=role,
        available_skills=_get_available_skill_names(),
        available_tools=_get_available_tool_names(),
    )


def _resolve_role_preset_with_available(
    *,
    role: str,
    available_skills: set[str],
    available_tools: set[str],
) -> dict[str, object] | None:
    raw = _ROLE_PRESET_CATALOG.get(role)
    if raw is None:
        return None

    preset = copy.deepcopy(raw)

    skill_allowlist = _normalize_preset_allowlist(
        list(preset.get("skill_allowlist", [])),
        available_skills,
    )
    tool_allowlist = _normalize_preset_allowlist(
        list(preset.get("tool_allowlist", [])),
        available_tools,
    )
    max_iterations = int(preset.get("max_tool_iterations", 1))

    preset["agent_config"] = {
        "skill_allowlist": skill_allowlist,
        "tool_allowlist": tool_allowlist,
        "max_tool_iterations": max_iterations,
    }
    preset["skill_allowlist"] = skill_allowlist
    preset["tool_allowlist"] = tool_allowlist
    preset["max_tool_iterations"] = max_iterations
    return preset


def _build_default_agent_config(role: str) -> dict[str, object] | None:
    if role not in _AUTO_APPLY_PRESET_ROLES:
        return None
    preset = _resolve_role_preset_with_available(
        role=role,
        available_skills=_get_available_skill_names(),
        available_tools=_get_available_tool_names(),
    )
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


async def create_agent(session: AsyncSession, agent_in: AgentCreate) -> Agent:
    """Register a new agent."""
    payload = agent_in.model_dump()
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
    available_skills = _get_available_skill_names()
    available_tools = _get_available_tool_names()
    presets: list[dict[str, object]] = []
    for role in _ROLE_PRESET_ORDER:
        preset = _resolve_role_preset_with_available(
            role=role,
            available_skills=available_skills,
            available_tools=available_tools,
        )
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
                            "tool_allowlist": [],
                            "max_tool_iterations": 1,
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


def list_agent_tool_options() -> list[dict[str, str]]:
    client = get_runtime_mcp_client()
    if client is None:
        return []
    tools = client.registry.list_tools()
    options = [
        {
            "name": tool.name,
            "description": tool.description,
            "server_name": tool.server_name,
        }
        for tool in tools
    ]
    options.sort(key=lambda item: item["name"])
    return options
