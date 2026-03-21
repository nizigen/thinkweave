"""Embedding helper with SHA256 content cache."""

from __future__ import annotations

import hashlib
from typing import Any

from app.memory.config import MemoryConfig, get_memory_config


class EmbeddingService:
    """Embedding wrapper that reuses llm_client.embed with hash cache."""

    def __init__(
        self,
        *,
        llm_client: Any,
        config: MemoryConfig | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._config = config or get_memory_config()
        self._cache: dict[str, list[float]] = {}

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def embed_text(self, text: str) -> list[float]:
        key = self._hash_text(text)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        vectors = await self._llm_client.embed(
            [text],
            model=self._config.memory_embedding_model,
        )
        vector = vectors[0]
        self._cache[key] = vector
        return vector

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        result: list[list[float]] = []
        missing: list[str] = []
        missing_indices: list[int] = []

        for idx, text in enumerate(texts):
            key = self._hash_text(text)
            cached = self._cache.get(key)
            if cached is None:
                missing.append(text)
                missing_indices.append(idx)
                result.append([])
            else:
                result.append(cached)

        if missing:
            vectors = await self._llm_client.embed(
                missing,
                model=self._config.memory_embedding_model,
            )
            for text, idx, vector in zip(missing, missing_indices, vectors):
                self._cache[self._hash_text(text)] = vector
                result[idx] = vector

        return result