"""Tool lifecycle tracking service for TEA-style runtime telemetry."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from app.config import settings
from app.utils.logger import logger

ToolLifecycleStatus = Literal["registered", "running", "success", "failed", "cleaned"]


@dataclass
class ToolLifecycleTransition:
    run_id: str
    tool_name: str
    status: ToolLifecycleStatus
    timestamp: float
    task_id: str = ""
    node_id: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolLifecycleRecord:
    run_id: str
    tool_name: str
    status: ToolLifecycleStatus
    task_id: str = ""
    node_id: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    transitions: list[ToolLifecycleTransition] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "tool_name": self.tool_name,
            "status": self.status,
            "task_id": self.task_id,
            "node_id": self.node_id,
            "error": self.error,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "transitions": [
                {
                    "run_id": item.run_id,
                    "tool_name": item.tool_name,
                    "status": item.status,
                    "timestamp": item.timestamp,
                    "task_id": item.task_id,
                    "node_id": item.node_id,
                    "error": item.error,
                    "metadata": dict(item.metadata),
                }
                for item in self.transitions
            ],
        }


class ToolLifecycleService:
    """In-memory lifecycle ledger with best-effort runtime event emission."""

    def __init__(self) -> None:
        self._records: dict[str, ToolLifecycleRecord] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _max_records() -> int:
        try:
            value = int(getattr(settings, "tool_lifecycle_max_records", 1000) or 1000)
        except Exception:
            value = 1000
        return max(100, value)

    def _prune_records_locked(self) -> None:
        limit = self._max_records()
        overflow = len(self._records) - limit
        if overflow <= 0:
            return
        oldest_ids = sorted(
            self._records.items(),
            key=lambda item: item[1].updated_at,
        )[:overflow]
        for run_id, _record in oldest_ids:
            self._records.pop(run_id, None)

    async def register(
        self,
        *,
        tool_name: str,
        task_id: str = "",
        node_id: str = "",
        metadata: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> ToolLifecycleRecord:
        normalized_name = str(tool_name or "").strip() or "unknown_tool"
        resolved_run_id = str(run_id or uuid.uuid4())
        now = time.time()
        record = ToolLifecycleRecord(
            run_id=resolved_run_id,
            tool_name=normalized_name,
            status="registered",
            task_id=str(task_id or ""),
            node_id=str(node_id or ""),
            metadata=dict(metadata or {}),
            created_at=now,
            updated_at=now,
        )
        record.transitions.append(
            ToolLifecycleTransition(
                run_id=record.run_id,
                tool_name=record.tool_name,
                status="registered",
                timestamp=now,
                task_id=record.task_id,
                node_id=record.node_id,
                metadata=dict(record.metadata),
            )
        )
        async with self._lock:
            self._records[record.run_id] = record
            self._prune_records_locked()
        await self._emit_transition(record.transitions[-1])
        return record

    async def set_status(
        self,
        *,
        run_id: str,
        status: ToolLifecycleStatus,
        metadata: dict[str, Any] | None = None,
        error: str = "",
    ) -> ToolLifecycleRecord:
        resolved_run_id = str(run_id or "").strip()
        if not resolved_run_id:
            raise ValueError("run_id is required")

        async with self._lock:
            record = self._records.get(resolved_run_id)
            if record is None:
                raise ValueError(f"unknown run_id: {resolved_run_id}")
            now = time.time()
            if metadata:
                merged = dict(record.metadata)
                merged.update(metadata)
                record.metadata = merged
            record.status = status
            record.error = str(error or "")
            record.updated_at = now
            transition = ToolLifecycleTransition(
                run_id=record.run_id,
                tool_name=record.tool_name,
                status=status,
                timestamp=now,
                task_id=record.task_id,
                node_id=record.node_id,
                error=record.error,
                metadata=dict(record.metadata),
            )
            record.transitions.append(transition)

        await self._emit_transition(transition)
        return record

    async def mark_running(self, *, run_id: str, metadata: dict[str, Any] | None = None) -> ToolLifecycleRecord:
        return await self.set_status(run_id=run_id, status="running", metadata=metadata)

    async def mark_success(self, *, run_id: str, metadata: dict[str, Any] | None = None) -> ToolLifecycleRecord:
        return await self.set_status(run_id=run_id, status="success", metadata=metadata)

    async def mark_failed(
        self,
        *,
        run_id: str,
        error: str,
        metadata: dict[str, Any] | None = None,
    ) -> ToolLifecycleRecord:
        return await self.set_status(
            run_id=run_id,
            status="failed",
            metadata=metadata,
            error=error,
        )

    async def mark_cleaned(self, *, run_id: str, metadata: dict[str, Any] | None = None) -> ToolLifecycleRecord:
        return await self.set_status(run_id=run_id, status="cleaned", metadata=metadata)

    async def get(self, run_id: str) -> dict[str, Any] | None:
        resolved_run_id = str(run_id or "").strip()
        if not resolved_run_id:
            return None
        async with self._lock:
            record = self._records.get(resolved_run_id)
            if record is None:
                return None
            return record.to_dict()

    async def list(self, *, status: ToolLifecycleStatus | None = None) -> list[dict[str, Any]]:
        async with self._lock:
            records = list(self._records.values())
        if status:
            records = [record for record in records if record.status == status]
        records.sort(key=lambda item: item.updated_at, reverse=True)
        return [record.to_dict() for record in records]

    async def clear(self) -> None:
        async with self._lock:
            self._records.clear()

    async def _emit_transition(self, transition: ToolLifecycleTransition) -> None:
        if not transition.task_id:
            return
        payload = {
            "run_id": transition.run_id,
            "tool_name": transition.tool_name,
            "status": transition.status,
            "timestamp": transition.timestamp,
            "error": transition.error,
            "metadata": transition.metadata,
        }
        try:
            from app.services import communicator

            await communicator.send_task_event(
                task_id=transition.task_id,
                node_id=transition.node_id,
                msg_type="tool_lifecycle",
                from_agent="tool_manager",
                payload=payload,
            )
        except Exception:
            logger.bind(
                run_id=transition.run_id,
                tool_name=transition.tool_name,
                status=transition.status,
            ).opt(exception=True).warning("tool lifecycle telemetry emit failed")


tool_lifecycle_service = ToolLifecycleService()
