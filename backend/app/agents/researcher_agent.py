"""Dedicated researcher agent for source-grounded evidence planning."""

from __future__ import annotations

from typing import Any

from app.agents.worker import WorkerAgent


class ResearcherAgent(WorkerAgent):
    """Specialized L2 agent for research planning and evidence collection."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs["role"] = "researcher"
        kwargs.setdefault("layer", 2)
        super().__init__(**kwargs)

    async def handle_task(self, ctx: dict[str, Any]) -> str:
        payload = dict(ctx.get("payload", {}))
        normalized_payload = {
            "title": payload.get("title", ctx.get("title", "")),
            "mode": payload.get("mode", "report"),
            "depth": payload.get("depth", ""),
            "full_outline": payload.get("full_outline", ""),
            "source_policy": payload.get("source_policy", ""),
            "research_keywords": payload.get("research_keywords", ""),
            "evidence_pool_seeds": payload.get("evidence_pool_seeds", ""),
            "evidence_pool_summary": payload.get("evidence_pool_summary", ""),
            "evidence_pool_markdown": payload.get("evidence_pool_markdown", ""),
            "target_words": payload.get("target_words", 10000),
            "memory_context": ctx.get("memory_context", payload.get("memory_context", "")),
        }

        return await super().handle_task(
            {
                **ctx,
                "agent_role": "researcher",
                "payload": normalized_payload,
                "title": ctx.get("title", normalized_payload["title"]),
            }
        )
