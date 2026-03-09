"""Tests for RAG module — chunker, embedder, retriever."""

from __future__ import annotations

import pytest

from app.rag.chunker import Chunk, TextChunker
from app.rag.embedder import Embedder
from app.rag.retriever import HybridRetriever, RetrievalResult
from tests.conftest import MockLLMClient


# ---------------------------------------------------------------------------
# Chunker Tests
# ---------------------------------------------------------------------------

SAMPLE_MARKDOWN = """# 第一章 引言

这是引言的内容，介绍了研究背景。

这是引言的第二段。

## 第二章 核心概念

核心概念包括量子比特和量子门。

量子比特是量子计算的基本单元。

## 第三章 总结

本文总结了量子计算的发展。
"""


class TestTextChunker:
    def test_chunk_by_chapter(self):
        chunker = TextChunker()
        chunks = chunker.chunk_by_chapter(SAMPLE_MARKDOWN)
        assert len(chunks) == 3
        assert chunks[0].chapter_index == 0
        assert "引言" in chunks[0].content
        assert chunks[1].chapter_index == 1
        assert "核心概念" in chunks[1].content
        assert chunks[2].chapter_index == 2

    def test_chunk_by_chapter_empty(self):
        chunker = TextChunker()
        chunks = chunker.chunk_by_chapter("")
        assert len(chunks) == 0

    def test_chunk_by_chapter_no_headings(self):
        chunker = TextChunker()
        chunks = chunker.chunk_by_chapter("plain text without headings")
        assert len(chunks) == 1
        assert chunks[0].content == "plain text without headings"

    def test_chunk_by_chapter_preserves_heading(self):
        chunker = TextChunker()
        chunks = chunker.chunk_by_chapter(SAMPLE_MARKDOWN)
        assert chunks[0].metadata["heading"].startswith("#")

    def test_chunk_by_paragraph_basic(self):
        chunker = TextChunker()
        text = "段落一的内容。\n\n段落二的内容。\n\n段落三的内容。"
        chunks = chunker.chunk_by_paragraph(text, max_tokens=50)
        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.source_type == "chapter"

    def test_chunk_by_paragraph_respects_max_tokens(self):
        chunker = TextChunker()
        # Each paragraph ~20 chars * 2 = ~40 tokens
        paras = ["这是段落内容。" * 5] * 10  # 10 paragraphs, each ~100 chars
        text = "\n\n".join(paras)
        chunks = chunker.chunk_by_paragraph(text, max_tokens=100)
        assert len(chunks) > 1

    def test_chunk_by_paragraph_empty(self):
        chunker = TextChunker()
        chunks = chunker.chunk_by_paragraph("")
        assert len(chunks) == 0

    def test_chunk_by_paragraph_with_chapter_index(self):
        chunker = TextChunker()
        chunks = chunker.chunk_by_paragraph("段落内容", chapter_index=3)
        assert chunks[0].chapter_index == 3

    def test_chunk_token_estimate(self):
        chunk = Chunk(content="Hello世界")
        assert chunk.token_estimate == len("Hello世界") * 2


# ---------------------------------------------------------------------------
# Embedder Tests
# ---------------------------------------------------------------------------

class TestEmbedder:
    @pytest.mark.asyncio
    async def test_embed_texts(self):
        mock = MockLLMClient()
        embedder = Embedder(mock)
        embeddings = await embedder.embed_texts(["text1", "text2"])
        assert len(embeddings) == 2
        assert len(embeddings[0]) == 1536  # MockLLMClient returns 1536-dim

    @pytest.mark.asyncio
    async def test_embed_empty(self):
        mock = MockLLMClient()
        embedder = Embedder(mock)
        embeddings = await embedder.embed_texts([])
        assert embeddings == []

    @pytest.mark.asyncio
    async def test_embed_chunks(self):
        mock = MockLLMClient()
        embedder = Embedder(mock)
        chunks = [
            Chunk(content="chunk1", chapter_index=0),
            Chunk(content="chunk2", chapter_index=1),
        ]
        results = await embedder.embed_chunks(chunks)
        assert len(results) == 2
        assert results[0][0].content == "chunk1"
        assert len(results[0][1]) == 1536

    @pytest.mark.asyncio
    async def test_embed_batching(self):
        mock = MockLLMClient()
        embedder = Embedder(mock, batch_size=2)
        texts = ["t1", "t2", "t3", "t4", "t5"]
        embeddings = await embedder.embed_texts(texts)
        assert len(embeddings) == 5
        # Should have called embed 3 times (2+2+1)
        embed_calls = [c for c in mock.call_log if c["method"] == "embed"]
        assert len(embed_calls) == 3


# ---------------------------------------------------------------------------
# Retriever Tests
# ---------------------------------------------------------------------------

class TestHybridRetriever:
    def test_rrf_fuse_empty(self):
        retriever = HybridRetriever()
        result = retriever._rrf_fuse([], [])
        assert result == []

    def test_rrf_fuse_single_list(self):
        retriever = HybridRetriever(k=60)
        semantic = [
            RetrievalResult(content="result A", score=0.9),
            RetrievalResult(content="result B", score=0.8),
        ]
        result = retriever._rrf_fuse(semantic, [])
        assert len(result) == 2
        # First result should have higher score
        assert result[0].content == "result A"
        assert result[0].score > result[1].score

    def test_rrf_fuse_both_lists(self):
        retriever = HybridRetriever(k=60)
        semantic = [
            RetrievalResult(content="both lists hit"),
            RetrievalResult(content="semantic only"),
        ]
        keyword = [
            RetrievalResult(content="both lists hit"),
            RetrievalResult(content="keyword only"),
        ]
        result = retriever._rrf_fuse(semantic, keyword)
        # "both lists hit" appears in both, should have highest score
        assert result[0].content == "both lists hit"
        assert result[0].score > result[1].score

    @pytest.mark.asyncio
    async def test_search_returns_empty_stub(self):
        retriever = HybridRetriever()
        results = await retriever.search("test query")
        # Stub implementation returns empty
        assert results == []

    def test_rrf_score_calculation(self):
        retriever = HybridRetriever(k=60)
        r1 = RetrievalResult(content="item")
        # Rank 0 in both lists
        result = retriever._rrf_fuse([r1], [r1])
        # Score should be 1/(60+1) + 1/(60+1) = 2/61
        expected = 2.0 / 61.0
        assert abs(result[0].score - expected) < 0.0001


# ---------------------------------------------------------------------------
# RetrievalMiddleware Tests
# ---------------------------------------------------------------------------

from app.rag.middleware import RetrievalContext, RetrievalMiddleware


class TestRetrievalContext:
    def test_empty_context(self):
        ctx = RetrievalContext(results=(), query="")
        assert ctx.is_empty
        assert ctx.to_prompt_text() == ""

    def test_context_with_results(self):
        results = (
            RetrievalResult(
                content="参考内容", score=0.85,
                source_type="chapter", chapter_index=1,
            ),
        )
        ctx = RetrievalContext(results=results, query="测试查询")
        assert not ctx.is_empty
        text = ctx.to_prompt_text()
        assert "参考内容" in text
        assert "相关度" in text
        assert "第1章" in text

    def test_prompt_text_max_results(self):
        results = tuple(
            RetrievalResult(content=f"内容{i}", score=0.5)
            for i in range(10)
        )
        ctx = RetrievalContext(results=results, query="q")
        text = ctx.to_prompt_text(max_results=3)
        assert "内容0" in text
        assert "内容2" in text
        assert "内容3" not in text


class TestRetrievalMiddlewareDisabled:
    """Tests for RetrievalMiddleware when rag_enabled=False (zero overhead)."""

    @pytest.mark.asyncio
    async def test_retrieve_returns_empty_when_disabled(self):
        mw = RetrievalMiddleware(enabled=False)
        ctx = await mw.retrieve("some query", task_id="t1")
        assert ctx.is_empty

    @pytest.mark.asyncio
    async def test_ingest_returns_zero_when_disabled(self):
        mw = RetrievalMiddleware(enabled=False)
        count = await mw.ingest("some text", task_id="t1")
        assert count == 0

    def test_components_not_initialized_when_disabled(self):
        mw = RetrievalMiddleware(enabled=False)
        assert mw._retriever is None
        assert mw._embedder is None
        assert mw._chunker is None
        assert mw.enabled is False


class TestRetrievalMiddlewareEnabled:
    """Tests for RetrievalMiddleware when rag_enabled=True."""

    @pytest.mark.asyncio
    async def test_components_initialized_when_enabled(self):
        mock = MockLLMClient()
        mw = RetrievalMiddleware(llm_client=mock, enabled=True)
        assert mw._retriever is not None
        assert mw._embedder is not None
        assert mw._chunker is not None
        assert mw.enabled is True

    @pytest.mark.asyncio
    async def test_retrieve_runs_search(self):
        mock = MockLLMClient()
        mw = RetrievalMiddleware(llm_client=mock, enabled=True)
        ctx = await mw.retrieve("量子计算基础", task_id="t1")
        # Stub retriever returns empty, but middleware ran without error
        assert ctx.is_empty
        assert ctx.query == "量子计算基础"

    @pytest.mark.asyncio
    async def test_retrieve_empty_query(self):
        mock = MockLLMClient()
        mw = RetrievalMiddleware(llm_client=mock, enabled=True)
        ctx = await mw.retrieve("", task_id="t1")
        assert ctx.is_empty

    @pytest.mark.asyncio
    async def test_retrieve_whitespace_query(self):
        mock = MockLLMClient()
        mw = RetrievalMiddleware(llm_client=mock, enabled=True)
        ctx = await mw.retrieve("   ", task_id="t1")
        assert ctx.is_empty

    @pytest.mark.asyncio
    async def test_ingest_chunks_and_embeds(self):
        mock = MockLLMClient()
        mw = RetrievalMiddleware(llm_client=mock, enabled=True)
        text = "段落一内容。\n\n段落二内容。\n\n段落三内容。"
        count = await mw.ingest(text, task_id="t1", source_type="chapter", chapter_index=2)
        assert count > 0
        # Verify embedder was called
        embed_calls = [c for c in mock.call_log if c["method"] == "embed"]
        assert len(embed_calls) >= 1

    @pytest.mark.asyncio
    async def test_ingest_empty_text(self):
        mock = MockLLMClient()
        mw = RetrievalMiddleware(llm_client=mock, enabled=True)
        count = await mw.ingest("", task_id="t1")
        assert count == 0

    @pytest.mark.asyncio
    async def test_custom_retriever_injected(self):
        """Verify dependency injection works for custom retriever."""
        mock = MockLLMClient()
        custom_retriever = HybridRetriever(k=30)
        mw = RetrievalMiddleware(
            llm_client=mock, retriever=custom_retriever, enabled=True
        )
        assert mw._retriever is custom_retriever
        assert mw._retriever._k == 30
