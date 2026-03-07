"""技能系统数据模型 — Skill dataclass + SkillType enum"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SkillType(str, Enum):
    """技能类型"""
    WRITING_STYLE = "writing_style"      # 写作风格模板（追加到system prompt）
    AGENT_BEHAVIOR = "agent_behavior"    # Agent行为定义（替换system prompt）


@dataclass(frozen=True)
class Skill:
    """单个技能的完整定义"""

    # --- YAML frontmatter fields ---
    name: str
    skill_type: SkillType
    description: str = ""
    applicable_roles: tuple[str, ...] = ()
    applicable_modes: tuple[str, ...] = ("all",)
    tools: tuple[str, ...] = ()
    model_preference: str | None = None

    # --- Parsed content ---
    content: str = ""           # Markdown body (without frontmatter)
    source_path: str = ""       # File path for debugging
