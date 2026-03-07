"""Tests for PromptLoader — loading, caching, variable rendering."""

import pytest

from app.utils.prompt_loader import PromptLoader


@pytest.fixture
def prompt_dir(tmp_path):
    """Create a temp prompt directory with test templates."""
    writer_dir = tmp_path / "writer"
    writer_dir.mkdir()
    (writer_dir / "write_chapter.md").write_text(
        "写第 {chapter_index} 章：{chapter_title}\n\n{chapter_description}",
        encoding="utf-8",
    )
    (writer_dir / "system.md").write_text(
        "你是一个专业的写作Agent。",
        encoding="utf-8",
    )

    reviewer_dir = tmp_path / "reviewer"
    reviewer_dir.mkdir()
    (reviewer_dir / "review_chapter.md").write_text(
        "审查第 {chapter_index} 章，评分标准：准确性、连贯性、风格。",
        encoding="utf-8",
    )
    return tmp_path


class TestPromptLoader:
    def test_load_basic(self, prompt_dir):
        loader = PromptLoader(prompt_dir)
        result = loader.load(
            "writer", "write_chapter",
            chapter_index="1",
            chapter_title="引言",
            chapter_description="介绍背景",
        )
        assert "写第 1 章：引言" in result
        assert "介绍背景" in result

    def test_load_system(self, prompt_dir):
        loader = PromptLoader(prompt_dir)
        result = loader.load_system("writer")
        assert "写作Agent" in result

    def test_load_without_variables(self, prompt_dir):
        loader = PromptLoader(prompt_dir)
        result = loader.load("writer", "system")
        assert "专业" in result

    def test_missing_variable_raises(self, prompt_dir):
        loader = PromptLoader(prompt_dir)
        with pytest.raises(KeyError):
            loader.load("writer", "write_chapter", chapter_index="1")

    def test_missing_template_raises(self, prompt_dir):
        loader = PromptLoader(prompt_dir)
        with pytest.raises(FileNotFoundError, match="not found"):
            loader.load("nonexistent", "action")

    def test_cache_reuses_content(self, prompt_dir):
        loader = PromptLoader(prompt_dir)
        loader.load("writer", "system")
        loader.load("writer", "system")
        assert "writer/system" in loader._cache
        assert len(loader._cache) == 1

    def test_reload_clears_cache(self, prompt_dir):
        loader = PromptLoader(prompt_dir)
        loader.load("writer", "system")
        assert len(loader._cache) == 1

        loader.reload()
        assert len(loader._cache) == 0

    def test_different_roles(self, prompt_dir):
        loader = PromptLoader(prompt_dir)
        writer = loader.load(
            "writer", "write_chapter",
            chapter_index="2",
            chapter_title="方法",
            chapter_description="描述方法论",
        )
        reviewer = loader.load(
            "reviewer", "review_chapter",
            chapter_index="2",
        )
        assert "写第 2 章" in writer
        assert "审查第 2 章" in reviewer


class TestPromptLoaderSecurity:
    """Path traversal prevention tests."""

    def test_slash_in_role_rejected(self, prompt_dir):
        loader = PromptLoader(prompt_dir)
        with pytest.raises(ValueError, match="Invalid role"):
            loader.load("../etc", "passwd")

    def test_backslash_in_role_rejected(self, prompt_dir):
        loader = PromptLoader(prompt_dir)
        with pytest.raises(ValueError, match="Invalid role"):
            loader.load("..\\etc", "passwd")

    def test_dotdot_in_action_rejected(self, prompt_dir):
        loader = PromptLoader(prompt_dir)
        with pytest.raises(ValueError, match="Invalid action"):
            loader.load("writer", "../../etc/passwd")

    def test_slash_in_action_rejected(self, prompt_dir):
        loader = PromptLoader(prompt_dir)
        with pytest.raises(ValueError, match="Invalid action"):
            loader.load("writer", "sub/action")

    def test_empty_role_rejected(self, prompt_dir):
        loader = PromptLoader(prompt_dir)
        with pytest.raises(ValueError, match="Invalid role"):
            loader.load("", "action")
