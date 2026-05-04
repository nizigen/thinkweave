"""混合检索器 — pgvector语义搜索 + PG全文搜索 + RRF融合排序

注意：数据库查询为 stub 实现，定义接口和算法逻辑。
实际的 pgvector/tsvector 查询在数据库表创建后补全。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from app.utils.logger import logger


@dataclass(frozen=True)
class RetrievalResult:
    """检索结果"""
    content: str
    score: float = 0.0
    source_type: str = ""
    chapter_index: int | None = None
    metadata: dict = field(default_factory=dict)


class HybridRetriever:
    """
    混合检索：pgvector余弦相似度 + PostgreSQL tsvector全文搜索。
    结果融合：RRF (Reciprocal Rank Fusion) 合并排序。
    """

    def __init__(
        self,
        k: int = 60,
        *,
        max_query_chars: int = 1024,
        min_query_chars: int = 2,
    ) -> None:
        """
        Args:
            k: RRF常数（默认60，标准值）
        """
        self._k = k
        self._max_query_chars = max(32, int(max_query_chars))
        self._min_query_chars = max(1, int(min_query_chars))

    async def search(
        self,
        query: str,
        task_id: str | None = None,
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        """
        混合检索。

        Args:
            query: 查询文本
            task_id: 限定任务范围（None表示全局）
            top_k: 返回结果数

        Returns:
            按相关性排序的检索结果
        """
        cleaned = self._normalize_query(query)
        if not self._is_valid_query(cleaned):
            logger.debug("rag query rejected by validation: '{}'", cleaned[:120])
            return []

        limit = max(1, int(top_k)) * 2
        semantic_results: list[RetrievalResult] = []
        keyword_results: list[RetrievalResult] = []
        try:
            semantic_results = await self._semantic_search(cleaned, task_id, limit)
        except Exception:
            logger.opt(exception=True).warning("semantic retrieval failed, fallback to keyword only")
            semantic_results = []

        if semantic_results:
            try:
                keyword_results = await self._keyword_search(cleaned, task_id, limit)
            except Exception:
                logger.opt(exception=True).warning("keyword retrieval failed after semantic results")
                keyword_results = []
            fused = self._rrf_fuse(semantic_results, keyword_results)
            return fused[: max(1, int(top_k))]

        try:
            keyword_results = await self._keyword_search(cleaned, task_id, limit)
        except Exception:
            logger.opt(exception=True).warning("keyword retrieval fallback failed")
            return []

        if not keyword_results:
            return []
        return keyword_results[: max(1, int(top_k))]

    async def _semantic_search(
        self, query: str, task_id: str | None, limit: int
    ) -> list[RetrievalResult]:
        """
        语义检索：pgvector余弦相似度。

        TODO: 实际实现需要：
        1. 通过 Embedder 将 query 转为向量
        2. 执行 SQL: SELECT *, 1 - (embedding <=> $query_vec) AS score
           FROM document_chunks WHERE task_id = $task_id
           ORDER BY embedding <=> $query_vec LIMIT $limit
        """
        return []

    async def _keyword_search(
        self, query: str, task_id: str | None, limit: int
    ) -> list[RetrievalResult]:
        """
        关键词检索：PostgreSQL tsvector全文搜索。

        TODO: 实际实现需要：
        1. 执行 SQL: SELECT *, ts_rank(tsv, plainto_tsquery('simple', $query)) AS score
           FROM document_chunks WHERE task_id = $task_id AND tsv @@ plainto_tsquery('simple', $query)
           ORDER BY score DESC LIMIT $limit
        """
        return []

    def _rrf_fuse(
        self,
        semantic: list[RetrievalResult],
        keyword: list[RetrievalResult],
    ) -> list[RetrievalResult]:
        """
        Reciprocal Rank Fusion — 合并两个排序列表。

        RRF score = sum(1 / (k + rank_i)) for each result list
        """
        scores: dict[str, float] = {}
        result_map: dict[str, RetrievalResult] = {}

        for rank, result in enumerate(semantic):
            key = hashlib.sha256(result.content.encode()).hexdigest()
            scores[key] = scores.get(key, 0) + 1.0 / (self._k + rank + 1)
            result_map[key] = result

        for rank, result in enumerate(keyword):
            key = hashlib.sha256(result.content.encode()).hexdigest()
            scores[key] = scores.get(key, 0) + 1.0 / (self._k + rank + 1)
            result_map[key] = result

        # Sort by fused score descending
        sorted_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)

        return [
            RetrievalResult(
                content=result_map[key].content,
                score=scores[key],
                source_type=result_map[key].source_type,
                chapter_index=result_map[key].chapter_index,
                metadata=dict(result_map[key].metadata),
            )
            for key in sorted_keys
        ]

    def _normalize_query(self, query: str) -> str:
        text = str(query or "")
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > self._max_query_chars:
            text = text[: self._max_query_chars]
        return text

    def _is_valid_query(self, query: str) -> bool:
        if not query:
            return False
        if len(query) < self._min_query_chars:
            return False
        if query.isdigit():
            return False
        tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", query)
        if not tokens:
            return False
        informative_tokens = [tok for tok in tokens if not tok.isdigit()]
        if not informative_tokens:
            return False
        if len("".join(informative_tokens)) < self._min_query_chars:
            return False
        return True
