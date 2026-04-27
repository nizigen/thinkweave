"""嵌入服务 — 通过LLMClient.embed()统一调用text-embedding-3-small"""

from __future__ import annotations

from app.rag.chunker import Chunk
from app.utils.llm_client import BaseLLMClient
from app.utils.logger import logger


class Embedder:
    """文本嵌入服务"""

    def __init__(self, llm_client: BaseLLMClient, batch_size: int = 20) -> None:
        self._llm_client = llm_client
        self._batch_size = batch_size

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        批量嵌入文本。

        Args:
            texts: 待嵌入的文本列表

        Returns:
            对应的嵌入向量列表
        """
        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            embeddings = await self._llm_client.embed(batch)
            all_embeddings.extend(embeddings)

        logger.bind(count=len(texts)).info("Texts embedded")
        return all_embeddings

    async def embed_chunks(self, chunks: list[Chunk]) -> list[tuple[Chunk, list[float]]]:
        """
        嵌入Chunk列表，返回 (chunk, embedding) 对。

        Args:
            chunks: 待嵌入的Chunk列表

        Returns:
            (Chunk, embedding_vector) 元组列表
        """
        texts = [c.content for c in chunks]
        embeddings = await self.embed_texts(texts)
        return list(zip(chunks, embeddings, strict=True))
