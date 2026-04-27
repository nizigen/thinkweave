"""Tests for skills system: parser, loader, types."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.skills.loader import SkillLoader
from app.skills.parser import SkillParseError, parse_skill
from app.skills.types import SkillType


VALID_SKILL_MD = """---
name: technical_report
type: writing_style
applicable_roles: [writer, outline]
applicable_modes: [report]
applicable_stages: [all]
tools: []
description: technical writing style
---

## Style
- Formal and objective tone
"""

BEHAVIOR_SKILL_MD = """---
name: researcher
type: agent_behavior
applicable_roles: [writer]
applicable_modes: [all]
applicable_stages: [writing]
priority: 10
tools: [web_search, brave_search]
model_preference: gpt-4o
description: research-first behavior
---

## Behavior
1. Search first
2. Synthesize sources
3. Draft output
"""


class TestSkillParser:
    def test_parse_valid_skill(self):
        skill = parse_skill(VALID_SKILL_MD)
        assert skill.name == "technical_report"
        assert skill.skill_type == SkillType.WRITING_STYLE
        assert skill.applicable_roles == ("writer", "outline")
        assert skill.applicable_modes == ("report",)
        assert skill.applicable_stages == ("all",)

    def test_parse_behavior_skill(self):
        skill = parse_skill(BEHAVIOR_SKILL_MD)
        assert skill.name == "researcher"
        assert skill.skill_type == SkillType.AGENT_BEHAVIOR
        assert skill.tools == ("web_search", "brave_search")
        assert skill.model_preference == "gpt-4o"
        assert skill.priority == 10

    def test_missing_frontmatter(self):
        with pytest.raises(SkillParseError, match="Missing YAML"):
            parse_skill("# Just markdown")

    def test_invalid_type(self):
        with pytest.raises(SkillParseError, match="Invalid type"):
            parse_skill("---\nname: test\ntype: bad\n---\ncontent")

    def test_default_fields(self):
        skill = parse_skill("---\nname: test\n---\ncontent")
        assert skill.skill_type == SkillType.WRITING_STYLE
        assert skill.applicable_modes == ("all",)
        assert skill.applicable_stages == ("all",)
        assert skill.priority == 100


class TestSkillLoader:
    def _create_skills_dir(self, tmp_path: Path) -> Path:
        styles_dir = tmp_path / "writing_styles"
        styles_dir.mkdir()
        (styles_dir / "report.md").write_text(VALID_SKILL_MD, encoding="utf-8")
        (styles_dir / "novel.md").write_text(
            "---\nname: novel\ntype: writing_style\n"
            "applicable_roles: [writer]\napplicable_modes: [novel]\n"
            "description: novel writing\n---\nnovel style",
            encoding="utf-8",
        )

        behaviors_dir = tmp_path / "agent_behaviors"
        behaviors_dir.mkdir()
        (behaviors_dir / "researcher.md").write_text(
            BEHAVIOR_SKILL_MD, encoding="utf-8"
        )

        (styles_dir / "broken.md").write_text("no frontmatter", encoding="utf-8")
        return tmp_path

    def test_load_all(self, tmp_path: Path):
        loader = SkillLoader(self._create_skills_dir(tmp_path))
        loader.load_all()
        assert len(loader.skills) == 3

    def test_match_by_role_mode(self, tmp_path: Path):
        loader = SkillLoader(self._create_skills_dir(tmp_path))
        loader.load_all()
        names = {s.name for s in loader.match("writer", "report")}
        assert "technical_report" in names
        assert "novel" not in names
        # stage-specific skill should not match unless stage is provided
        assert "researcher" not in names

    def test_match_honors_stage(self, tmp_path: Path):
        loader = SkillLoader(self._create_skills_dir(tmp_path))
        loader.load_all()
        names = {s.name for s in loader.match("writer", "report", stage="writing")}
        assert "researcher" in names

    def test_get_prompt_injection(self, tmp_path: Path):
        loader = SkillLoader(self._create_skills_dir(tmp_path))
        loader.load_all()
        injection = loader.get_prompt_injection("writer", "report", stage="writing")
        assert "technical_report" in injection
        assert "researcher" in injection

    def test_get_prompt_injection_empty(self, tmp_path: Path):
        loader = SkillLoader(self._create_skills_dir(tmp_path))
        loader.load_all()
        injection = loader.get_prompt_injection("reviewer", "novel")
        assert injection == ""

    def test_reload(self, tmp_path: Path):
        skills_dir = self._create_skills_dir(tmp_path)
        loader = SkillLoader(skills_dir)
        loader.load_all()
        assert len(loader.skills) == 3

        (skills_dir / "new_skill.md").write_text(
            "---\nname: new_skill\ntype: writing_style\n---\ncontent",
            encoding="utf-8",
        )
        loader.reload()
        assert len(loader.skills) == 4

    def test_nonexistent_directory(self, tmp_path: Path):
        loader = SkillLoader(tmp_path / "nonexistent")
        loader.load_all()
        assert len(loader.skills) == 0
