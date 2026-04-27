"""YAML frontmatter + Markdown解析器 — 从.md文件提取技能定义"""

from __future__ import annotations

import yaml

from app.skills.types import Skill, SkillType


class SkillParseError(Exception):
    """技能文件解析失败"""


def parse_skill(text: str, source_path: str = "") -> Skill:
    """
    解析 Markdown + YAML frontmatter 格式的技能文件。

    格式：
        ---
        name: technical_report
        type: writing_style
        ...
        ---
        ## Markdown content here

    Args:
        text: 完整文件内容
        source_path: 文件路径（用于错误提示）

    Returns:
        Skill dataclass

    Raises:
        SkillParseError: frontmatter缺失或格式错误
    """
    stripped = text.strip()
    if not stripped.startswith("---"):
        raise SkillParseError(
            f"Missing YAML frontmatter in {source_path or 'input'}"
        )

    # Split on second '---'
    parts = stripped.split("---", 2)
    if len(parts) < 3:
        raise SkillParseError(
            f"Incomplete YAML frontmatter in {source_path or 'input'}"
        )

    yaml_text = parts[1].strip()
    content = parts[2].strip()

    try:
        meta = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        raise SkillParseError(f"Invalid YAML in {source_path or 'input'}: {e}") from e

    if not isinstance(meta, dict):
        raise SkillParseError(
            f"YAML frontmatter must be a mapping in {source_path or 'input'}"
        )

    # Required fields
    name = meta.get("name")
    if not name:
        raise SkillParseError(f"Missing 'name' in {source_path or 'input'}")

    raw_type = meta.get("type", "writing_style")
    try:
        skill_type = SkillType(raw_type)
    except ValueError as e:
        raise SkillParseError(
            f"Invalid type '{raw_type}' in {source_path or 'input'}, "
            f"must be one of {[t.value for t in SkillType]}"
        ) from e

    # Optional fields
    applicable_roles = meta.get("applicable_roles", [])
    if isinstance(applicable_roles, str):
        applicable_roles = [applicable_roles]

    applicable_modes = meta.get("applicable_modes", ["all"])
    if isinstance(applicable_modes, str):
        applicable_modes = [applicable_modes]

    applicable_stages = meta.get("applicable_stages", ["all"])
    if isinstance(applicable_stages, str):
        applicable_stages = [applicable_stages]

    tools = meta.get("tools", [])
    if isinstance(tools, str):
        tools = [tools]

    return Skill(
        name=name,
        skill_type=skill_type,
        description=meta.get("description", ""),
        applicable_roles=tuple(applicable_roles),
        applicable_modes=tuple(applicable_modes),
        applicable_stages=tuple(applicable_stages),
        tools=tuple(tools),
        model_preference=meta.get("model_preference"),
        priority=int(meta.get("priority", 100)),
        content=content,
        source_path=source_path,
    )
