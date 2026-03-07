"""技能加载器 — 扫描skills/目录，按role+mode匹配适用技能"""

from __future__ import annotations

from pathlib import Path

from app.skills.parser import SkillParseError, parse_skill
from app.skills.types import Skill, SkillType
from app.utils.logger import logger


class SkillLoader:
    """从文件系统加载技能，按Agent角色和任务模式匹配"""

    def __init__(self, skills_dir: str | Path | None = None) -> None:
        if skills_dir is None:
            skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
        self.skills_dir = Path(skills_dir).resolve()
        self._skills: dict[str, Skill] = {}

    @property
    def skills(self) -> dict[str, Skill]:
        return dict(self._skills)

    def _is_safe_path(self, file_path: Path) -> bool:
        """确保解析后的路径在skills_dir内（防止符号链接穿越）"""
        try:
            file_path.resolve().relative_to(self.skills_dir)
            return True
        except ValueError:
            return False

    def load_all(self) -> None:
        """扫描 skills/ 目录，解析所有 .md 文件"""
        new_skills: dict[str, Skill] = {}

        if not self.skills_dir.exists():
            logger.warning(f"Skills directory not found: {self.skills_dir}")
            self._skills = new_skills
            return

        for md_file in self.skills_dir.rglob("*.md"):
            if not self._is_safe_path(md_file):
                logger.warning(f"Skipping file outside skills dir: {md_file}")
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
                skill = parse_skill(text, source_path=str(md_file))
                new_skills[skill.name] = skill
                logger.debug(f"Loaded skill: {skill.name}")
            except SkillParseError as e:
                logger.warning(f"Skipping invalid skill file: {e}")

        self._skills = new_skills
        logger.info(f"Loaded {len(self._skills)} skills from {self.skills_dir}")

    def match(self, role: str, mode: str) -> list[Skill]:
        """
        按 Agent角色 + 任务模式 匹配适用技能。

        匹配规则：
        - applicable_roles 包含该role，或 applicable_roles 为空（通配）
        - applicable_modes 包含该mode 或包含 "all"
        """
        matched = []
        for skill in self._skills.values():
            role_match = not skill.applicable_roles or role in skill.applicable_roles
            mode_match = "all" in skill.applicable_modes or mode in skill.applicable_modes
            if role_match and mode_match:
                matched.append(skill)
        return matched

    def get_prompt_injection(self, role: str, mode: str) -> str:
        """返回拼接后的技能文本，供注入 system prompt"""
        matched = self.match(role, mode)
        if not matched:
            return ""
        parts = []
        for skill in matched:
            if skill.skill_type == SkillType.WRITING_STYLE:
                parts.append(f"\n## 写作规范：{skill.name}\n{skill.content}")
            else:
                parts.append(f"\n## 行为定义：{skill.name}\n{skill.content}")
        return "\n".join(parts)

    def get(self, name: str) -> Skill | None:
        """按名称获取技能"""
        return self._skills.get(name)

    def reload(self) -> None:
        """重新加载所有技能文件"""
        self.load_all()
