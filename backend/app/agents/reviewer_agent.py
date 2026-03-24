"""Dedicated reviewer agent for chapter quality checks."""

from __future__ import annotations

from typing import Any

from app.agents.worker import WorkerAgent


class ReviewerAgent(WorkerAgent):
    """Specialized L2 agent for chapter review."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs["role"] = "reviewer"
        kwargs.setdefault("layer", 2)
        super().__init__(**kwargs)

    async def handle_task(self, ctx: dict[str, Any]) -> str:
        payload = dict(ctx.get("payload", {}))
        normalized_payload = {
            "chapter_index": payload.get("chapter_index", ""),
            "chapter_title": payload.get("chapter_title", ""),
            "chapter_content": payload.get("chapter_content", ""),
            "chapter_description": payload.get("chapter_description", ""),
            "overlap_findings": payload.get("overlap_findings", "none"),
            "topic_claims": payload.get("topic_claims", {}),
            "assigned_evidence": payload.get("assigned_evidence", []),
        }

        return await super().handle_task(
            {
                **ctx,
                "agent_role": "reviewer",
                "payload": normalized_payload,
            }
        )
