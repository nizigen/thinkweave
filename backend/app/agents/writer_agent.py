"""Dedicated writer agent for chapter drafting."""

from __future__ import annotations

from typing import Any

from app.agents.worker import WorkerAgent


class WriterAgent(WorkerAgent):
    """Specialized L2 agent for writing chapters."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs["role"] = "writer"
        kwargs.setdefault("layer", 2)
        super().__init__(**kwargs)

    async def handle_task(self, ctx: dict[str, Any]) -> str:
        incoming_role = str(ctx.get("agent_role") or "writer").strip().lower()
        if incoming_role != "writer":
            return await super().handle_task(ctx)
        payload = dict(ctx.get("payload", {}))
        normalized_payload = {
            "depth": payload.get("depth", ""),
            "chapter_index": payload.get("chapter_index", ""),
            "chapter_title": payload.get("chapter_title", ""),
            "full_outline": payload.get("full_outline", ""),
            "chapter_description": payload.get("chapter_description", ""),
            "context_bridges": payload.get("context_bridges", ""),
            "memory_context": ctx.get("memory_context", payload.get("memory_context", "")),
            "topic_claims": payload.get("topic_claims", {}),
            "assigned_evidence": payload.get("assigned_evidence", []),
            "source_policy": payload.get("source_policy", ""),
            "research_protocol": payload.get("research_protocol", ""),
            "research_keywords": payload.get("research_keywords", ""),
            "evidence_pool_summary": payload.get("evidence_pool_summary", ""),
            "evidence_pool_markdown": payload.get("evidence_pool_markdown", ""),
            "target_words": payload.get("target_words", ""),
        }

        return await super().handle_task(
            {
                **ctx,
                "agent_role": "writer",
                "payload": normalized_payload,
            }
        )
