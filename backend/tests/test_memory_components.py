"""Tests for embedding cache and image registry."""

from __future__ import annotations

import pytest

from app.memory.embedding import EmbeddingService
from app.memory.image_registry import ImageRegistry


class FakeLLMEmbedClient:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str], *, model: str | None = None):
        self.calls.append(list(texts))
        return [[float(i + 1)] * 4 for i, _ in enumerate(texts)]


class TestEmbeddingService:
    @pytest.mark.asyncio
    async def test_embed_text_uses_cache(self):
        llm = FakeLLMEmbedClient()
        service = EmbeddingService(llm_client=llm)

        first = await service.embed_text("alpha")
        second = await service.embed_text("alpha")

        assert first == second
        assert len(llm.calls) == 1

    @pytest.mark.asyncio
    async def test_embed_batch_partial_cache(self):
        llm = FakeLLMEmbedClient()
        service = EmbeddingService(llm_client=llm)

        await service.embed_text("alpha")
        vectors = await service.embed_batch(["alpha", "beta"])

        assert len(vectors) == 2
        assert len(llm.calls) == 2
        assert llm.calls[1] == ["beta"]


class TestImageRegistry:
    @pytest.mark.asyncio
    async def test_cross_chapter_duplicate_blocked(self):
        reg = ImageRegistry()
        ok_1 = await reg.try_register(1, "https://x/img.png")
        ok_2 = await reg.try_register(2, "https://x/img.png")

        assert ok_1 is True
        assert ok_2 is False

    @pytest.mark.asyncio
    async def test_release_chapter_allows_reuse(self):
        reg = ImageRegistry()
        await reg.try_register(1, "https://x/img.png")
        await reg.release_chapter(1)
        ok = await reg.try_register(2, "https://x/img.png")

        assert ok is True
