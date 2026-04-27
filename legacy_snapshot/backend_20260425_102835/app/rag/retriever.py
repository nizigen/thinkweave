"""混合检索器 — pgvector语义搜索 + PG全文搜索 + RRF融合排序

注意：数据库查询为 stub 实现，定义接口和算法逻辑。
实际的 pgvector/tsvector 查询在数据库表创建后补全。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


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

    def __init__(self, k: int = 60) -> None:
        """
        Args:
            k: RRF常数（默认60，标准值）
        """
        self._k = k

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
        # 并行执行语义检索和关键词检索
        semantic_results = await self._semantic_search(query, task_id, top_k * 2)
        keyword_results = await self._keyword_search(query, task_id, top_k * 2)

        # RRF融合
        fused = self._rrf_fuse(semantic_results, keyword_results)

        return fused[:top_k]

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
