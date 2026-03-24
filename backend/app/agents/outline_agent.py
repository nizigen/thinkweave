"""Dedicated outline agent for long-text generation."""

from __future__ import annotations

from typing import Any

from app.agents.worker import WorkerAgent


class OutlineAgent(WorkerAgent):
    """Specialized L2 agent for outline generation."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs["role"] = "outline"
        kwargs.setdefault("layer", 2)
        super().__init__(**kwargs)

    async def handle_task(self, ctx: dict[str, Any]) -> str:
        payload = dict(ctx.get("payload", {}))
        normalized_payload = {
            "title": payload.get("title", ctx.get("title", "")),
            "mode": payload.get("mode", "report"),
            "target_words": payload.get("target_words", 10000),
            "draft_text": payload.get("draft_text", ""),
            "review_comments": payload.get("review_comments", ""),
            "style_requirements": payload.get("style_requirements", ""),
        }

        return await super().handle_task(
            {
                **ctx,
                "agent_role": "outline",
                "payload": normalized_payload,
                "title": ctx.get("title", normalized_payload["title"]),
            }
        )
