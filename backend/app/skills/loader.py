"""Skills loader: scan skills directory and match by role/mode/stage."""

from __future__ import annotations

from pathlib import Path

from app.skills.parser import SkillParseError, parse_skill
from app.skills.types import Skill, SkillType
from app.utils.logger import logger


class SkillLoader:
    """Load skills from filesystem and resolve prompt injections."""
    USER_CLAUDE_WRITING_RELATIVE_FILES = (
        "awesome-ai-research-writing/skill.md",
        "dan-koe-content-system/skill.md",
        "ai-research-skills/20-ml-paper-writing/skill.md",
        "baoyu-suite/baoyu-format-markdown/skill.md",
        "baoyu-suite/baoyu-markdown-to-html/skill.md",
        "baoyu-suite/baoyu-url-to-markdown/skill.md",
        "marketing-skills/social-content/skill.md",
    )

    def __init__(
        self,
        skills_dir: str | Path | None = None,
        extra_skill_dirs: list[str | Path] | None = None,
    ) -> None:
        if skills_dir is None:
            backend_skills = Path(__file__).resolve().parent.parent.parent / "skills"
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            project_claude_skills = project_root / ".claude" / "skills"
            self.user_claude_skills_dir = Path.home() / ".claude" / "skills"
            self.skill_dirs = [
                backend_skills.resolve(),
                project_claude_skills.resolve(),
                self.user_claude_skills_dir.resolve(),
            ]
        else:
            self.skill_dirs = [Path(skills_dir).resolve()]
            self.user_claude_skills_dir = None

        if extra_skill_dirs:
            for path in extra_skill_dirs:
                self.skill_dirs.append(Path(path).resolve())
        self._skills: dict[str, Skill] = {}

    @property
    def skills(self) -> dict[str, Skill]:
        return dict(self._skills)

    def _is_safe_path(self, file_path: Path) -> bool:
        resolved = file_path.resolve()
        for root in self.skill_dirs:
            try:
                resolved.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    def _iter_skill_files(self, skills_root: Path):
        if skills_root.name == "skills" and skills_root.parent.name == ".claude":
            yield from skills_root.rglob("SKILL.md")
            return
        yield from skills_root.rglob("*.md")

    def _is_claude_skill_path(self, file_path: Path) -> bool:
        parts = set(file_path.resolve().parts)
        return ".claude" in parts and "skills" in parts

    def _is_user_claude_skill_path(self, file_path: Path) -> bool:
        if self.user_claude_skills_dir is None:
            return False
        try:
            file_path.resolve().relative_to(self.user_claude_skills_dir.resolve())
            return True
        except ValueError:
            return False

    def _is_whitelisted_user_claude_skill_file(self, file_path: Path) -> bool:
        if not self._is_user_claude_skill_path(file_path):
            return True
        relative = (
            str(file_path.resolve().relative_to(self.user_claude_skills_dir.resolve()))
            .lower()
            .replace("\\", "/")
        )
        return relative in self.USER_CLAUDE_WRITING_RELATIVE_FILES

    def _is_writing_related_claude_skill(self, skill: Skill) -> bool:
        # Restrict matching to name/description to avoid broad instruction-body noise.
        text = " ".join(
            [
                str(skill.name or ""),
                str(skill.description or ""),
            ]
        ).lower()
        keywords = (
            "write",
            "writing",
            "writer",
            "report",
            "novel",
            "story",
            "outline",
            "chapter",
            "article",
            "blog",
            "longform",
            "copywriting",
            "editorial",
            "technical_report",
            "写作",
            "文案",
            "报告",
            "小说",
            "大纲",
            "章节",
            "长文",
            "文章",
        )
        return any(keyword in text for keyword in keywords)

    def load_all(self) -> None:
        new_skills: dict[str, Skill] = {}
        roots_found = 0
        for skills_root in self.skill_dirs:
            if not skills_root.exists():
                continue
            roots_found += 1
            for md_file in self._iter_skill_files(skills_root):
                if not self._is_safe_path(md_file):
                    logger.warning(f"Skipping file outside skills dirs: {md_file}")
                    continue
                if not self._is_whitelisted_user_claude_skill_file(md_file):
                    continue
                try:
                    text = md_file.read_text(encoding="utf-8")
                    skill = parse_skill(text, source_path=str(md_file))
                    if self._is_claude_skill_path(md_file):
                        # User-level .claude skills are restricted by explicit path whitelist.
                        if not self._is_user_claude_skill_path(md_file):
                            if not self._is_writing_related_claude_skill(skill):
                                continue
                    # Keep backend skills authoritative when names collide.
                    if skill.name in new_skills:
                        existing = Path(str(new_skills[skill.name].source_path))
                        if "backend" in existing.parts and "skills" in existing.parts:
                            continue
                    new_skills[skill.name] = skill
                    logger.debug(f"Loaded skill: {skill.name}")
                except SkillParseError as exc:
                    logger.warning(f"Skipping invalid skill file: {exc}")

        if roots_found == 0:
            logger.warning(f"Skills directories not found: {self.skill_dirs}")
            self._skills = new_skills
            return

        self._skills = new_skills
        logger.info(f"Loaded {len(self._skills)} skills from {self.skill_dirs}")

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
