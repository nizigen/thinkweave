"""Dedicated runtime agent for unified tool lifecycle operations."""

from __future__ import annotations

import json
from typing import Any, cast

from app.agents.base_agent import BaseAgent
from app.services.tool_lifecycle import (
    ToolLifecycleStatus,
    tool_lifecycle_service,
)

_VALID_STATUSES: set[str] = {"registered", "running", "success", "failed", "cleaned"}
_VALID_ACTIONS: set[str] = {"register", "update", "get", "cleanup", "list"}


class ToolManagerAgent(BaseAgent):
    """Layer 1.5 agent managing tool lifecycle transitions."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs["role"] = "tool_manager"
        kwargs.setdefault("layer", 1)
        super().__init__(**kwargs)

    async def handle_task(self, ctx: dict[str, Any]) -> str:
        payload = dict(ctx.get("payload", {}))
        action = str(payload.get("action", "list") or "list").strip().lower()
        if action not in _VALID_ACTIONS:
            raise ValueError(f"invalid lifecycle action: {action!r}")
        task_id = str(ctx.get("task_id", payload.get("task_id", "")) or "")
        node_id = str(ctx.get("node_id", payload.get("node_id", "")) or "")

        if action == "register":
            tool_name = str(payload.get("tool_name", payload.get("title", "")) or "").strip()
            if not tool_name:
                raise ValueError("tool_name is required for register action")
            record = await tool_lifecycle_service.register(
                tool_name=tool_name,
                task_id=task_id,
                node_id=node_id,
                metadata=payload.get("metadata"),
                run_id=payload.get("run_id"),
            )
            return json.dumps(record.to_dict(), ensure_ascii=False)

        if action == "update":
            run_id = str(payload.get("run_id", "") or "").strip()
            status_raw = str(payload.get("status", "") or "").strip().lower()
            if not run_id:
                raise ValueError("run_id is required for update action")
            if status_raw not in _VALID_STATUSES:
                raise ValueError(f"invalid lifecycle status: {status_raw!r}")
            status = cast(ToolLifecycleStatus, status_raw)
            record = await tool_lifecycle_service.set_status(
                run_id=run_id,
                status=status,
                metadata=payload.get("metadata"),
                error=str(payload.get("error", "") or ""),
            )
            return json.dumps(record.to_dict(), ensure_ascii=False)

        if action == "get":
            run_id = str(payload.get("run_id", "") or "").strip()
            if not run_id:
                raise ValueError("run_id is required for get action")
            record = await tool_lifecycle_service.get(run_id)
            if record is None:
                raise ValueError(f"unknown run_id: {run_id}")
            return json.dumps(record, ensure_ascii=False)

        if action == "cleanup":
            run_id = str(payload.get("run_id", "") or "").strip()
            if not run_id:
                raise ValueError("run_id is required for cleanup action")
            record = await tool_lifecycle_service.mark_cleaned(
                run_id=run_id,
                metadata=payload.get("metadata"),
            )
            return json.dumps(record.to_dict(), ensure_ascii=False)

        status_filter = payload.get("status")
        if status_filter is None:
            items = await tool_lifecycle_service.list()
        else:
            status_raw = str(status_filter).strip().lower()
            if status_raw not in _VALID_STATUSES:
                raise ValueError(f"invalid lifecycle status: {status_raw!r}")
            items = await tool_lifecycle_service.list(
                status=cast(ToolLifecycleStatus, status_raw)
            )
        return json.dumps({"items": items}, ensure_ascii=False)
