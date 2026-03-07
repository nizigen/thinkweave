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
