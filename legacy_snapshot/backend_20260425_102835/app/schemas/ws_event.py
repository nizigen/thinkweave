"""WebSocket event schemas used by the monitoring pipeline."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskEvent(BaseModel):
    type: str
    task_id: str
    node_id: str = ""
    from_agent: str = ""
    timestamp: float = 0.0
    payload: dict[str, Any] = Field(default_factory=dict)


class ConnectedEvent(TaskEvent):
    type: Literal["connected"] = "connected"


class NodeUpdateEvent(TaskEvent):
    type: Literal["node_update"] = "node_update"


class LogEvent(TaskEvent):
    type: Literal["log"] = "log"


class AgentStatusEvent(TaskEvent):
    type: Literal["agent_status"] = "agent_status"


class TaskDoneEvent(TaskEvent):
    type: Literal["task_done"] = "task_done"


class ChapterPreviewEvent(TaskEvent):
    type: Literal["chapter_preview"] = "chapter_preview"


class ReviewScoreEvent(TaskEvent):
    type: Literal["review_score"] = "review_score"


class ConsistencyResultEvent(TaskEvent):
    type: Literal["consistency_result"] = "consistency_result"


class DagUpdateEvent(TaskEvent):
    type: Literal["dag_update"] = "dag_update"
