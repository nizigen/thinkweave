"""上下文管理器 — 三层记忆架构 + 渐进式披露 + 上下文压缩

参考 OpenClaw 三层记忆 + claude-mem 渐进式披露设计。
"""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import Any

from app.utils.llm_client import BaseLLMClient
from app.utils.logger import logger


# ---------------------------------------------------------------------------
# Memory Layers
# ---------------------------------------------------------------------------

class ContextLayer(str, Enum):
    WORKING = "working"        # 当前Agent工作状态（Redis Hash，生命周期=单次任务）
    TASK = "task"              # 任务级共享上下文（Redis+PG，生命周期=整个Task）
    PERSISTENT = "persistent"  # 跨任务持久知识（PG+pgvector，生命周期=永久）


# ---------------------------------------------------------------------------
# Context Manager
# ---------------------------------------------------------------------------

# Agent角色 → 上下文组装配置（不可变）
_ROLE_CONTEXT_CONFIG: MappingProxyType = MappingProxyType({
    "writer": MappingProxyType({
        "include_full_outline": False,     # 只需大纲摘要
        "include_chapter_detail": True,    # 本章完整描述
        "include_glossary": True,          # 术语表
        "include_review_feedback": True,   # 相关审查反馈
        "include_other_chapters": False,   # 不需要其他章节全文
    }),
    "reviewer": MappingProxyType({
        "include_full_outline": True,      # 完整大纲供参考
        "include_chapter_detail": True,    # 待审章节全文
        "include_glossary": False,
        "include_review_feedback": False,
        "include_other_chapters": False,
    }),
    "consistency": MappingProxyType({
        "include_full_outline": True,      # 完整大纲
        "include_chapter_detail": False,
        "include_glossary": True,
        "include_other_chapters": True,    # 各章摘要（非全文）
        "include_review_feedback": False,
    }),
    "outline": MappingProxyType({
        "include_full_outline": False,
        "include_chapter_detail": False,
        "include_glossary": False,
        "include_review_feedback": False,
        "include_other_chapters": False,
    }),
})


class ContextManager:
    """三层记忆 + 渐进式披露 + 上下文压缩"""

    def __init__(self, llm_client: BaseLLMClient | None = None) -> None:
        self._llm_client = llm_client
        # In-memory stores (will be backed by Redis/PG in production)
        self._working: dict[str, dict[str, Any]] = {}
        self._task: dict[str, dict[str, Any]] = {}

    # -- Working Memory (per agent instance) --------------------------------

    def set_working(self, agent_id: str, key: str, value: Any) -> None:
        """设置Agent工作记忆"""
        if agent_id not in self._working:
            self._working[agent_id] = {}
        self._working[agent_id][key] = value

    def get_working(self, agent_id: str, key: str, default: Any = None) -> Any:
        """获取Agent工作记忆"""
        return self._working.get(agent_id, {}).get(key, default)

    def clear_working(self, agent_id: str) -> None:
        """清理Agent工作记忆（任务完成后）"""
        self._working.pop(agent_id, None)

    # -- Task Memory (shared across agents within a task) -------------------

    def set_task_data(self, task_id: str, key: str, value: Any) -> None:
        """设置任务级共享数据"""
        if task_id not in self._task:
            self._task[task_id] = {}
        self._task[task_id][key] = value

    def get_task_data(self, task_id: str, key: str, default: Any = None) -> Any:
        """获取任务级共享数据"""
        return self._task.get(task_id, {}).get(key, default)

    def set_chapter_summary(
        self, task_id: str, chapter_index: int, summary: str
    ) -> None:
        """保存章节摘要到Task Memory"""
        existing = self.get_task_data(task_id, "chapter_summaries", {})
        updated = {**existing, chapter_index: summary}
        self.set_task_data(task_id, "chapter_summaries", updated)

    def get_chapter_summaries(self, task_id: str) -> dict[int, str]:
        """获取所有章节摘要"""
        return self.get_task_data(task_id, "chapter_summaries", {})

    def set_glossary(self, task_id: str, glossary: dict[str, str]) -> None:
        """设置术语表"""
        self.set_task_data(task_id, "glossary", glossary)

    def get_glossary(self, task_id: str) -> dict[str, str]:
        """获取术语表"""
        return self.get_task_data(task_id, "glossary", {})

    def clear_task(self, task_id: str) -> None:
        """清理任务级数据"""
        self._task.pop(task_id, None)

    # -- Context Building (progressive disclosure) --------------------------

    def build_context(
        self,
        agent_role: str,
        task_id: str,
        *,
        system_prompt: str = "",
        outline: str = "",
        outline_summary: str = "",
        chapter_index: int | None = None,
        chapter_content: str = "",
        chapter_description: str = "",
        review_feedback: str = "",
    ) -> list[dict[str, str]]:
        """
        渐进式披露：按Agent角色组装不同粒度的上下文。

        - Writer: 系统提示 + 大纲摘要 + 本章详情 + 术语表 + 审查反馈
        - Reviewer: 系统提示 + 完整大纲 + 待审章节全文
        - Consistency: 系统提示 + 完整大纲 + 各章摘要
        - Outline: 系统提示（最少上下文）

        组装顺序遵循Prompt前缀优化（静态在前，变量在后）。
        """
        config = _ROLE_CONTEXT_CONFIG.get(agent_role, {})
        messages: list[dict[str, str]] = []

        # [1] System prompt (static per role)
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # [2] Build user context parts
        parts: list[str] = []

        # Outline (full or summary)
        if config.get("include_full_outline") and outline:
            parts.append(f"## 完整大纲\n{outline}")
        elif outline_summary:
            parts.append(f"## 大纲摘要\n{outline_summary}")

        # Glossary
        if config.get("include_glossary"):
            glossary = self.get_glossary(task_id)
            if glossary:
                glossary_text = "\n".join(
                    f"- **{term}**: {definition}"
                    for term, definition in glossary.items()
                )
                parts.append(f"## 术语表\n{glossary_text}")

        # Chapter summaries (for consistency agent)
        if config.get("include_other_chapters"):
            summaries = self.get_chapter_summaries(task_id)
            if summaries:
                summary_text = "\n\n".join(
                    f"### 第{idx+1}章摘要\n{s}"
                    for idx, s in sorted(summaries.items())
                )
                parts.append(f"## 各章节摘要\n{summary_text}")

        # Chapter detail (for writer/reviewer)
        if config.get("include_chapter_detail"):
            if chapter_description:
                parts.append(f"## 本章要求\n{chapter_description}")
            if chapter_content:
                parts.append(f"## 章节内容\n{chapter_content}")

        # Review feedback (for writer revision)
        if config.get("include_review_feedback") and review_feedback:
            parts.append(f"## 审查反馈\n{review_feedback}")

        if parts:
            messages.append({"role": "user", "content": "\n\n".join(parts)})

        return messages

    # -- Context Compression -----------------------------------------------

    async def compress_if_needed(
        self,
        messages: list[dict[str, str]],
        max_ratio: float = 0.75,
        model_max_tokens: int = 128000,
    ) -> list[dict[str, str]]:
        """
        上下文压缩：当消息总token超过模型窗口的max_ratio时，
        用LLM摘要中间部分，保留系统提示和最近消息。

        粗略估算：1个中文字符 ≈ 2 tokens, 1个英文单词 ≈ 1.3 tokens
        """
        if not self._llm_client:
            return messages

        estimated_tokens = sum(
            len(m.get("content", "")) * 2 for m in messages
        )
        threshold = int(model_max_tokens * max_ratio)

        if estimated_tokens <= threshold:
            return messages

        logger.info(
            f"Context compression triggered: "
            f"~{estimated_tokens} tokens > {threshold} threshold"
        )

        # Keep system prompt (first) and recent messages (last 2)
        if len(messages) <= 3:
            return messages

        preserved_head = messages[:1]   # system prompt
        preserved_tail = messages[-2:]  # recent messages
        middle = messages[1:-2]

        if not middle:
            return messages

        # Summarize the middle section
        middle_text = "\n\n".join(
            f"[{m['role']}]: {m['content']}" for m in middle
        )
        summary = await self._llm_client.chat(
            messages=[{
                "role": "user",
                "content": (
                    "请将以下对话历史压缩为简洁摘要，保留关键信息和决策。"
                    "只输出摘要内容：\n\n" + middle_text
                ),
            }],
            role="manager",  # Use cheaper model for compression
            temperature=0.3,
        )

        compressed = (
            preserved_head
            + [{"role": "user", "content": f"[以下是之前对话的摘要]\n{summary}"}]
            + preserved_tail
        )

        logger.info(
            f"Context compressed: {len(messages)} → {len(compressed)} messages"
        )
        return compressed

    # -- Chapter Summary Generation ----------------------------------------

    async def summarize_chapter(
        self, task_id: str, chapter_index: int, content: str
    ) -> str:
        """
        章节写完后生成摘要，存入Task Memory供其他Agent引用。

        Args:
            task_id: 任务ID
            chapter_index: 章节索引
            content: 章节全文

        Returns:
            摘要文本
        """
        if not self._llm_client:
            # Fallback: take first 200 chars
            summary = content[:200] + ("..." if len(content) > 200 else "")
            self.set_chapter_summary(task_id, chapter_index, summary)
            return summary

        summary = await self._llm_client.chat(
            messages=[{
                "role": "user",
                "content": (
                    "请用2-3句话概括以下章节的核心内容、关键论点和结论。"
                    "只输出摘要：\n\n" + content
                ),
            }],
            role="manager",
            temperature=0.3,
        )

        self.set_chapter_summary(task_id, chapter_index, summary)
        logger.bind(task_id=task_id, chapter_index=chapter_index).info(
            "Chapter summary generated"
        )
        return summary
