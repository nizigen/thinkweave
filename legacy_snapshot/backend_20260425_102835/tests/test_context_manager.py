"""Tests for context_manager — three-layer memory, progressive disclosure, compression."""

from __future__ import annotations

import pytest

from app.utils.context_manager import ContextManager, ContextLayer
from tests.conftest import MockLLMClient


# ---------------------------------------------------------------------------
# Working Memory
# ---------------------------------------------------------------------------

class TestWorkingMemory:
    def test_set_and_get(self):
        cm = ContextManager()
        cm.set_working("agent1", "key1", "value1")
        assert cm.get_working("agent1", "key1") == "value1"

    def test_get_default(self):
        cm = ContextManager()
        assert cm.get_working("agent1", "missing") is None
        assert cm.get_working("agent1", "missing", "default") == "default"

    def test_clear_working(self):
        cm = ContextManager()
        cm.set_working("agent1", "key1", "value1")
        cm.clear_working("agent1")
        assert cm.get_working("agent1", "key1") is None

    def test_clear_nonexistent_agent(self):
        cm = ContextManager()
        cm.clear_working("nonexistent")  # Should not raise

    def test_multiple_agents_isolated(self):
        cm = ContextManager()
        cm.set_working("agent1", "key", "val1")
        cm.set_working("agent2", "key", "val2")
        assert cm.get_working("agent1", "key") == "val1"
        assert cm.get_working("agent2", "key") == "val2"


# ---------------------------------------------------------------------------
# Task Memory
# ---------------------------------------------------------------------------

class TestTaskMemory:
    def test_set_and_get_task_data(self):
        cm = ContextManager()
        cm.set_task_data("task1", "outline", "# 大纲内容")
        assert cm.get_task_data("task1", "outline") == "# 大纲内容"

    def test_chapter_summaries(self):
        cm = ContextManager()
        cm.set_chapter_summary("task1", 0, "第一章摘要")
        cm.set_chapter_summary("task1", 1, "第二章摘要")
        summaries = cm.get_chapter_summaries("task1")
        assert summaries == {0: "第一章摘要", 1: "第二章摘要"}

    def test_glossary(self):
        cm = ContextManager()
        cm.set_glossary("task1", {"量子比特": "qubit的中文翻译"})
        glossary = cm.get_glossary("task1")
        assert glossary == {"量子比特": "qubit的中文翻译"}

    def test_clear_task(self):
        cm = ContextManager()
        cm.set_task_data("task1", "key", "value")
        cm.set_chapter_summary("task1", 0, "summary")
        cm.clear_task("task1")
        assert cm.get_task_data("task1", "key") is None
        assert cm.get_chapter_summaries("task1") == {}

    def test_multiple_tasks_isolated(self):
        cm = ContextManager()
        cm.set_task_data("task1", "key", "val1")
        cm.set_task_data("task2", "key", "val2")
        assert cm.get_task_data("task1", "key") == "val1"
        assert cm.get_task_data("task2", "key") == "val2"


# ---------------------------------------------------------------------------
# Progressive Disclosure (build_context)
# ---------------------------------------------------------------------------

class TestBuildContext:
    def test_writer_context(self):
        cm = ContextManager()
        cm.set_glossary("task1", {"量子": "quantum"})

        messages = cm.build_context(
            "writer", "task1",
            system_prompt="你是一个写作Agent",
            outline_summary="大纲摘要内容",
            chapter_description="写第1章",
            review_feedback="建议增加案例",
        )

        assert messages[0]["role"] == "system"
        assert "写作Agent" in messages[0]["content"]
        user_content = messages[1]["content"]
        assert "大纲摘要" in user_content
        assert "量子" in user_content          # glossary included
        assert "写第1章" in user_content         # chapter detail
        assert "增加案例" in user_content         # review feedback

    def test_writer_no_full_outline(self):
        cm = ContextManager()
        messages = cm.build_context(
            "writer", "task1",
            outline="完整大纲很长很长",
            outline_summary="大纲摘要",
        )
        user_content = messages[0]["content"]
        assert "大纲摘要" in user_content
        assert "完整大纲很长很长" not in user_content

    def test_reviewer_gets_full_outline(self):
        cm = ContextManager()
        messages = cm.build_context(
            "reviewer", "task1",
            system_prompt="你是审查Agent",
            outline="完整大纲内容",
            chapter_content="待审章节全文",
        )
        user_content = messages[1]["content"]
        assert "完整大纲内容" in user_content
        assert "待审章节全文" in user_content

    def test_consistency_gets_chapter_summaries(self):
        cm = ContextManager()
        cm.set_chapter_summary("task1", 0, "第一章要点")
        cm.set_chapter_summary("task1", 1, "第二章要点")

        messages = cm.build_context(
            "consistency", "task1",
            outline="完整大纲",
        )
        user_content = messages[0]["content"]
        assert "第一章" in user_content
        assert "第二章" in user_content

    def test_outline_minimal_context(self):
        cm = ContextManager()
        messages = cm.build_context(
            "outline", "task1",
            system_prompt="你是大纲Agent",
        )
        assert len(messages) == 1  # Only system prompt
        assert messages[0]["role"] == "system"

    def test_empty_context_no_user_message(self):
        cm = ContextManager()
        messages = cm.build_context("outline", "task1")
        assert len(messages) == 0

    def test_unknown_role_defaults_to_minimal(self):
        cm = ContextManager()
        messages = cm.build_context(
            "unknown_role", "task1",
            system_prompt="test",
            outline="outline",
        )
        # Unknown role has no config, so only system prompt
        assert len(messages) == 1


# ---------------------------------------------------------------------------
# Context Compression
# ---------------------------------------------------------------------------

class TestContextCompression:
    @pytest.mark.asyncio
    async def test_no_compression_when_under_threshold(self):
        cm = ContextManager(llm_client=MockLLMClient())
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "short message"},
        ]
        result = await cm.compress_if_needed(messages, model_max_tokens=128000)
        assert result == messages

    @pytest.mark.asyncio
    async def test_compression_triggered(self):
        mock = MockLLMClient()
        cm = ContextManager(llm_client=mock)

        # Create messages that exceed threshold
        long_content = "这是一段很长的内容。" * 5000
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": long_content},
            {"role": "assistant", "content": long_content},
            {"role": "user", "content": "recent question"},
            {"role": "assistant", "content": "recent answer"},
        ]
        result = await cm.compress_if_needed(
            messages, max_ratio=0.01, model_max_tokens=1000
        )
        # Should be compressed: system + summary + last 2
        assert len(result) < len(messages)
        assert result[0]["content"] == "system prompt"
        assert "recent answer" in result[-1]["content"]

    @pytest.mark.asyncio
    async def test_no_compression_without_llm_client(self):
        cm = ContextManager(llm_client=None)
        messages = [{"role": "user", "content": "x" * 100000}]
        result = await cm.compress_if_needed(messages)
        assert result == messages

    @pytest.mark.asyncio
    async def test_few_messages_not_compressed(self):
        cm = ContextManager(llm_client=MockLLMClient())
        messages = [
            {"role": "system", "content": "x" * 100000},
            {"role": "user", "content": "x" * 100000},
            {"role": "assistant", "content": "x" * 100000},
        ]
        result = await cm.compress_if_needed(
            messages, max_ratio=0.01, model_max_tokens=100
        )
        assert result == messages  # Only 3 messages, can't split


# ---------------------------------------------------------------------------
# Chapter Summary
# ---------------------------------------------------------------------------

class TestChapterSummary:
    @pytest.mark.asyncio
    async def test_summarize_with_llm(self):
        mock = MockLLMClient()
        cm = ContextManager(llm_client=mock)
        summary = await cm.summarize_chapter("task1", 0, "长文本内容...")
        assert len(summary) > 0
        assert cm.get_chapter_summaries("task1")[0] == summary
        # Verify LLM was called
        assert len(mock.call_log) == 1

    @pytest.mark.asyncio
    async def test_summarize_without_llm_fallback(self):
        cm = ContextManager(llm_client=None)
        content = "A" * 300
        summary = await cm.summarize_chapter("task1", 0, content)
        assert len(summary) == 203  # 200 chars + "..."
        assert summary.endswith("...")

    @pytest.mark.asyncio
    async def test_summarize_short_content_no_ellipsis(self):
        cm = ContextManager(llm_client=None)
        summary = await cm.summarize_chapter("task1", 0, "短文")
        assert summary == "短文"
