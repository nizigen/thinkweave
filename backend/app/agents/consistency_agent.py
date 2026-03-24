"""Dedicated consistency agent for full-document checks."""

from __future__ import annotations

from typing import Any

from app.agents.worker import WorkerAgent


class ConsistencyAgent(WorkerAgent):
    """Specialized L2 agent for cross-chapter consistency checks."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs["role"] = "consistency"
        kwargs.setdefault("layer", 2)
        super().__init__(**kwargs)

    async def handle_task(self, ctx: dict[str, Any]) -> str:
        payload = dict(ctx.get("payload", {}))
        normalized_payload = {
            "chapters_summary": payload.get("chapters_summary", ""),
            "full_text": payload.get("full_text", ""),
            "topic_claims": payload.get("topic_claims", []),
            "chapter_metadata": payload.get("chapter_metadata", []),
        }

        return await super().handle_task(
            {
                **ctx,
                "agent_role": "consistency",
                "payload": normalized_payload,
            }
        )
