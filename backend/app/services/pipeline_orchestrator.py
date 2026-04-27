"""ThinkWeave pipeline orchestrator skeleton (Phase 1, Wave 1).

This module introduces a stage-oriented orchestration layer above DAG planning,
so we can progressively migrate from legacy DAG-only semantics to a semantic
stage pipeline without breaking existing APIs.
"""

from __future__ import annotations

from typing import Any

from app.schemas.task import DAGSchema
from app.services.task_decomposer import decompose_task
from app.utils.llm_client import BaseLLMClient

STAGES: list[tuple[str, str]] = [
    ("SCOPING", "主题解析与检索计划"),
    ("RESEARCH", "检索与去重"),
    ("OUTLINE", "提纲生成"),
    ("DRAFT", "分章节草稿"),
    ("REVIEW", "引用绑定与一致性"),
    ("ASSEMBLY", "终稿拼装与润色"),
    ("QA", "质量校验"),
]


class PipelineOrchestrator:
    """Stage-oriented wrapper around DAG decomposition.

    Phase 1 keeps DAG execution engine in place, while routing planning through
    this orchestrator to make stage metadata first-class in checkpoint data.
    """

    def __init__(self, llm_client: BaseLLMClient) -> None:
        self.llm_client = llm_client

    async def plan_task(
        self,
        *,
        title: str,
        mode: str,
        depth: str,
        target_words: int,
    ) -> tuple[DAGSchema, dict[str, Any]]:
        dag = await decompose_task(
            title=title,
            mode=mode,
            depth=depth,
            target_words=target_words,
            llm_client=self.llm_client,
        )
        meta = {
            "pipeline": {
                "version": "thinkweave.pipeline.v1",
                "stages": [{"code": code, "name": name} for code, name in STAGES],
                "active_stage": "OUTLINE",
                "mode": "stage_orchestrated",
                "execution_graph": "dag_preserved",
            }
        }
        return dag, meta
