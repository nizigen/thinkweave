"""Skills loader: scan skills directory and match by role/mode/stage."""

from __future__ import annotations

from pathlib import Path

from app.skills.parser import SkillParseError, parse_skill
from app.skills.types import Skill, SkillType
from app.utils.logger import logger


class SkillLoader:
    """Load skills from filesystem and resolve prompt injections."""

    def __init__(self, skills_dir: str | Path | None = None) -> None:
        if skills_dir is None:
            skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
        self.skills_dir = Path(skills_dir).resolve()
        self._skills: dict[str, Skill] = {}

    @property
    def skills(self) -> dict[str, Skill]:
        return dict(self._skills)

    def _is_safe_path(self, file_path: Path) -> bool:
        try:
            file_path.resolve().relative_to(self.skills_dir)
            return True
        except ValueError:
            return False

    def load_all(self) -> None:
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
            except SkillParseError as exc:
                logger.warning(f"Skipping invalid skill file: {exc}")

        self._skills = new_skills
        logger.info(f"Loaded {len(self._skills)} skills from {self.skills_dir}")

    def match(self, role: str, mode: str, stage: str | None = None) -> list[Skill]:
        """Match skills by role + mode + stage."""
        matched: list[Skill] = []
        stage_value = stage or "all"

        for skill in self._skills.values():
            role_match = not skill.applicable_roles or role in skill.applicable_roles
            mode_match = "all" in skill.applicable_modes or mode in skill.applicable_modes
            stage_match = (
                "all" in skill.applicable_stages
                or stage_value in skill.applicable_stages
            )
            if role_match and mode_match and stage_match:
                matched.append(skill)

        matched.sort(key=lambda item: (item.priority, item.name))
        return matched

    def get_prompt_injection(
        self, role: str, mode: str, stage: str | None = None
    ) -> str:
        matched = self.match(role, mode, stage=stage)
        if not matched:
            return ""

        parts: list[str] = []
        for skill in matched:
            if skill.skill_type == SkillType.WRITING_STYLE:
                parts.append(f"\n## Writing Style ({skill.name})\n{skill.content}")
            else:
                parts.append(f"\n## Agent Behavior ({skill.name})\n{skill.content}")
        return "\n".join(parts)

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def reload(self) -> None:
        self.load_all()
