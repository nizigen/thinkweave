"""RAG 检索中间件 — rag_enabled=false 时零开销

RetrievalMiddleware 作为 Agent 处理流水线的一环，在 Agent 执行任务前
自动注入相关上下文。当 rag_enabled=False 时直接透传，无任何性能开销。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.rag.chunker import Chunk, TextChunker
from app.rag.embedder import Embedder
from app.rag.retriever import HybridRetriever, RetrievalResult
from app.utils.llm_client import BaseLLMClient
from app.utils.logger import logger


@dataclass(frozen=True)
class RetrievalContext:
    """检索结果封装 — 传递给 Agent 作为附加上下文"""
    results: tuple[RetrievalResult, ...]
    query: str

    @property
    def is_empty(self) -> bool:
        return len(self.results) == 0

    def to_prompt_text(self, max_results: int = 5) -> str:
        """将检索结果格式化为 Prompt 文本片段"""
        if self.is_empty:
            return ""

        lines = ["## 相关参考资料\n"]
        for i, r in enumerate(self.results[:max_results], 1):
            source = f"[来源: {r.source_type}"
            if r.chapter_index is not None:
                source += f", 第{r.chapter_index}章"
            source += f", 相关度: {r.score:.3f}]"
            lines.append(f"### 参考 {i} {source}\n{r.content}\n")

        return "\n".join(lines)


_EMPTY_CONTEXT = RetrievalContext(results=(), query="")


class RetrievalMiddleware:
    """
    RAG 检索中间件。

    当 rag_enabled=True 时：
    - 接收 Agent 的任务描述作为查询
    - 执行混合检索（语义 + 关键词）
    - 返回 RetrievalContext 供 Agent 拼入 Prompt

    当 rag_enabled=False 时：
    - retrieve() 立即返回空结果，零开销
    - 所有内部组件不会被初始化
    """

    def __init__(
        self,
        llm_client: BaseLLMClient | None = None,
        retriever: HybridRetriever | None = None,
        embedder: Embedder | None = None,
        chunker: TextChunker | None = None,
        *,
        enabled: bool | None = None,
    ) -> None:
        self._enabled = enabled if enabled is not None else settings.rag_enabled

        # 仅在启用时初始化组件（懒初始化避免无用开销）
        if self._enabled:
            self._retriever = retriever or HybridRetriever()
            self._embedder = embedder or (Embedder(llm_client) if llm_client else None)
            self._chunker = chunker or TextChunker()
        else:
            self._retriever = None
            self._embedder = None
            self._chunker = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def retrieve(
        self,
        query: str,
        task_id: str | None = None,
        top_k: int = 5,
    ) -> RetrievalContext:
        """
        执行检索，返回可直接拼入 Prompt 的 RetrievalContext。

        当 rag_enabled=False 时立即返回空结果。
        """
        if not self._enabled:
            return _EMPTY_CONTEXT

        if not query.strip():
            return _EMPTY_CONTEXT

        if self._retriever is None:
            logger.warning("RAG enabled but retriever not initialized")
            return _EMPTY_CONTEXT

        results = await self._retriever.search(
            query=query,
            task_id=task_id,
            top_k=top_k,
        )

        logger.bind(
            task_id=task_id,
            query_len=len(query),
            result_count=len(results),
        ).info("RAG retrieval completed")

        return RetrievalContext(
            results=tuple(results),
            query=query,
        )

    async def ingest(
        self,
        text: str,
        task_id: str,
        source_type: str = "chapter",
        chapter_index: int | None = None,
    ) -> int:
        """
        将文本分块并嵌入，存入检索库。

        当 rag_enabled=False 时直接返回 0。

        Returns:
            分块数量
        """
        if not self._enabled:
            return 0

        if self._chunker is None or self._embedder is None:
            logger.warning("RAG enabled but chunker/embedder not initialized")
            return 0

        # 按段落分块
        chunks = self._chunker.chunk_by_paragraph(
            text,
            chapter_index=chapter_index,
        )

        # 覆盖 source_type
        typed_chunks = [
            Chunk(
                content=c.content,
                source_type=source_type,
                chapter_index=chapter_index if chapter_index is not None else c.chapter_index,
                metadata={**c.metadata, "task_id": task_id},
            )
            for c in chunks
        ]

        # 嵌入（实际存储在完成 DB 集成后补充）
        await self._embedder.embed_chunks(typed_chunks)

        logger.bind(
            task_id=task_id,
            chunk_count=len(typed_chunks),
            source_type=source_type,
        ).info("RAG ingestion completed")

        return len(typed_chunks)
