"""Tests for skills system — parser, loader, types."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.skills.parser import SkillParseError, parse_skill
from app.skills.loader import SkillLoader
from app.skills.types import Skill, SkillType


# ---------------------------------------------------------------------------
# Parser Tests
# ---------------------------------------------------------------------------

VALID_SKILL_MD = """---
name: technical_report
type: writing_style
applicable_roles: [writer, outline]
applicable_modes: [report]
tools: []
description: 技术报告写作规范
---

## 写作风格
- 使用正式、客观的学术语气
"""

BEHAVIOR_SKILL_MD = """---
name: researcher
type: agent_behavior
applicable_roles: [writer]
applicable_modes: [all]
tools: [web_search, brave_search]
model_preference: gpt-4o
description: 深度研究型写作
---

## 行为定义
1. 先搜索相关资料
2. 整理素材
3. 撰写内容
"""


class TestSkillParser:
    def test_parse_valid_skill(self):
        skill = parse_skill(VALID_SKILL_MD)
        assert skill.name == "technical_report"
        assert skill.skill_type == SkillType.WRITING_STYLE
        assert skill.applicable_roles == ("writer", "outline")
        assert skill.applicable_modes == ("report",)
        assert "学术语气" in skill.content

    def test_parse_behavior_skill(self):
        skill = parse_skill(BEHAVIOR_SKILL_MD)
        assert skill.name == "researcher"
        assert skill.skill_type == SkillType.AGENT_BEHAVIOR
        assert skill.tools == ("web_search", "brave_search")
        assert skill.model_preference == "gpt-4o"

    def test_parse_preserves_source_path(self):
        skill = parse_skill(VALID_SKILL_MD, source_path="/some/path.md")
        assert skill.source_path == "/some/path.md"

    def test_missing_frontmatter(self):
        with pytest.raises(SkillParseError, match="Missing YAML"):
            parse_skill("# Just markdown\nNo frontmatter here")

    def test_incomplete_frontmatter(self):
        with pytest.raises(SkillParseError, match="Incomplete"):
            parse_skill("---\nname: test\n")

    def test_missing_name(self):
        with pytest.raises(SkillParseError, match="name"):
            parse_skill("---\ntype: writing_style\n---\ncontent")

    def test_invalid_type(self):
        with pytest.raises(SkillParseError, match="Invalid type"):
            parse_skill("---\nname: test\ntype: invalid_type\n---\ncontent")

    def test_default_type_is_writing_style(self):
        skill = parse_skill("---\nname: test\n---\ncontent")
        assert skill.skill_type == SkillType.WRITING_STYLE

    def test_string_roles_converted_to_list(self):
        skill = parse_skill("---\nname: test\napplicable_roles: writer\n---\ncontent")
        assert skill.applicable_roles == ("writer",)

    def test_string_modes_converted_to_list(self):
        skill = parse_skill("---\nname: test\napplicable_modes: report\n---\ncontent")
        assert skill.applicable_modes == ("report",)

    def test_default_modes_is_all(self):
        skill = parse_skill("---\nname: test\n---\ncontent")
        assert skill.applicable_modes == ("all",)

    def test_invalid_yaml(self):
        with pytest.raises(SkillParseError, match="Invalid YAML"):
            parse_skill("---\n: : invalid: yaml: [[\n---\ncontent")

    def test_skill_is_frozen(self):
        skill = parse_skill(VALID_SKILL_MD)
        with pytest.raises(AttributeError):
            skill.name = "changed"


# ---------------------------------------------------------------------------
# Loader Tests
# ---------------------------------------------------------------------------

class TestSkillLoader:
    def _create_skills_dir(self, tmp_path: Path) -> Path:
        """Create a temporary skills directory with test files."""
        styles_dir = tmp_path / "writing_styles"
        styles_dir.mkdir()

        (styles_dir / "report.md").write_text(VALID_SKILL_MD, encoding="utf-8")
        (styles_dir / "novel.md").write_text(
            "---\nname: novel\ntype: writing_style\n"
            "applicable_roles: [writer]\napplicable_modes: [novel]\n"
            "description: 小说写作\n---\n小说写作规范",
            encoding="utf-8",
        )

        behaviors_dir = tmp_path / "agent_behaviors"
        behaviors_dir.mkdir()
        (behaviors_dir / "researcher.md").write_text(
            BEHAVIOR_SKILL_MD, encoding="utf-8"
        )

        # Invalid file to test error handling
        (styles_dir / "broken.md").write_text(
            "no frontmatter here", encoding="utf-8"
        )

        return tmp_path

    def test_load_all(self, tmp_path: Path):
        skills_dir = self._create_skills_dir(tmp_path)
        loader = SkillLoader(skills_dir)
        loader.load_all()
        # 3 valid skills (broken.md skipped)
        assert len(loader.skills) == 3

    def test_match_by_role_and_mode(self, tmp_path: Path):
        skills_dir = self._create_skills_dir(tmp_path)
        loader = SkillLoader(skills_dir)
        loader.load_all()

        matched = loader.match("writer", "report")
        names = {s.name for s in matched}
        assert "technical_report" in names
        # researcher has applicable_modes=["all"], so it matches
        assert "researcher" in names
        # novel only matches mode=novel
        assert "novel" not in names

    def test_match_novel_mode(self, tmp_path: Path):
        skills_dir = self._create_skills_dir(tmp_path)
        loader = SkillLoader(skills_dir)
        loader.load_all()

        matched = loader.match("writer", "novel")
        names = {s.name for s in matched}
        assert "novel" in names
        assert "technical_report" not in names

    def test_match_outline_role(self, tmp_path: Path):
        skills_dir = self._create_skills_dir(tmp_path)
        loader = SkillLoader(skills_dir)
        loader.load_all()

        matched = loader.match("outline", "report")
        names = {s.name for s in matched}
        assert "technical_report" in names
        # researcher only applies to writer role
        assert "researcher" not in names

    def test_get_prompt_injection(self, tmp_path: Path):
        skills_dir = self._create_skills_dir(tmp_path)
        loader = SkillLoader(skills_dir)
        loader.load_all()

        injection = loader.get_prompt_injection("writer", "report")
        assert "写作规范" in injection
        assert "technical_report" in injection

    def test_get_prompt_injection_empty(self, tmp_path: Path):
        skills_dir = self._create_skills_dir(tmp_path)
        loader = SkillLoader(skills_dir)
        loader.load_all()

        injection = loader.get_prompt_injection("reviewer", "novel")
        # reviewer not in any skill's applicable_roles
        assert injection == ""

    def test_get_by_name(self, tmp_path: Path):
        skills_dir = self._create_skills_dir(tmp_path)
        loader = SkillLoader(skills_dir)
        loader.load_all()

        skill = loader.get("technical_report")
        assert skill is not None
        assert skill.name == "technical_report"
        assert loader.get("nonexistent") is None

    def test_reload(self, tmp_path: Path):
        skills_dir = self._create_skills_dir(tmp_path)
        loader = SkillLoader(skills_dir)
        loader.load_all()
        assert len(loader.skills) == 3

        # Add another skill file
        (skills_dir / "new_skill.md").write_text(
            "---\nname: new_skill\ntype: writing_style\n---\nnew content",
            encoding="utf-8",
        )
        loader.reload()
        assert len(loader.skills) == 4

    def test_nonexistent_directory(self, tmp_path: Path):
        loader = SkillLoader(tmp_path / "nonexistent")
        loader.load_all()
        assert len(loader.skills) == 0

    def test_load_real_skills_directory(self):
        """Test loading from the actual project skills/ directory."""
        skills_dir = Path(__file__).resolve().parent.parent / "skills"
        if not skills_dir.exists():
            pytest.skip("Project skills/ directory not found")
        loader = SkillLoader(skills_dir)
        loader.load_all()
        assert len(loader.skills) >= 2  # technical_report + novel
