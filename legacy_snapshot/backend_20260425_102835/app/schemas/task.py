"""Task Pydantic Schema"""

import uuid
from typing import Any, Literal
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Constants (must be defined before schemas that reference them)
# ---------------------------------------------------------------------------

VALID_MODES = {"report", "novel", "custom"}
VALID_DEPTHS = {"quick", "standard", "deep"}
VALID_AGENT_ROLES = {"outline", "researcher", "writer", "reviewer", "consistency"}


# ---------------------------------------------------------------------------
# API Schemas
# ---------------------------------------------------------------------------

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=6, max_length=500)
    mode: str = "report"
    depth: str = "standard"
    target_words: int = Field(default=10000, ge=500, le=200000)
    draft_text: str | None = Field(default=None, max_length=200_000)
    review_comments: str | None = Field(default=None, max_length=50_000)

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in VALID_MODES:
            raise ValueError(f"Invalid mode '{v}', must be one of {sorted(VALID_MODES)}")
        return v

    @field_validator("depth")
    @classmethod
    def validate_depth(cls, v: str) -> str:
        if v not in VALID_DEPTHS:
            raise ValueError(f"Invalid depth '{v}', must be one of {sorted(VALID_DEPTHS)}")
        return v


class TaskRead(BaseModel):
    id: uuid.UUID
    title: str
    mode: str
    status: str
    fsm_state: str
    word_count: int
    depth: str
    target_words: int
    error_message: str | None = None
    created_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class TaskNodeRead(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    title: str
    agent_role: str | None
    assigned_agent: uuid.UUID | None
    status: str
    depends_on: list[uuid.UUID] | None
    retry_count: int
    started_at: datetime | None
    finished_at: datetime | None
    required_capabilities: list[str] = Field(default_factory=list)
    preferred_agents: list[str] = Field(default_factory=list)
    routing_mode: Literal["auto", "capability_first", "strict_bind"] = "auto"
    routing_reason: str | None = None
    routing_status: str | None = None

    model_config = {"from_attributes": True}


class TaskDetailRead(TaskRead):
    output_text: str | None = None
    checkpoint_data: dict[str, Any] = Field(default_factory=dict)
    nodes: list[TaskNodeRead] = Field(default_factory=list)


class TaskControlSkipRequest(BaseModel):
    node_id: uuid.UUID


class TaskControlRetryRequest(BaseModel):
    node_id: uuid.UUID


# ---------------------------------------------------------------------------
# DAG Validation Schemas (for LLM JSON response parsing)
# ---------------------------------------------------------------------------


class DAGNodeSchema(BaseModel):
    """单个DAG节点的schema — 用于校验LLM返回的JSON"""
    id: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=1, max_length=500)
    role: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    preferred_agents: list[str] = Field(default_factory=list)
    routing_mode: Literal["auto", "capability_first", "strict_bind"] = "auto"

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if v not in VALID_AGENT_ROLES:
            raise ValueError(
                f"Invalid role '{v}', must be one of {VALID_AGENT_ROLES}"
            )
        return v

    @field_validator("required_capabilities", "preferred_agents")
    @classmethod
    def normalize_string_list(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in v:
            token = str(item or "").strip()
            if not token:
                continue
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(token)
        return out


class DAGSchema(BaseModel):
    """DAG整体schema — 用于校验LLM返回的JSON"""
    nodes: list[DAGNodeSchema] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Input Validation Result
# ---------------------------------------------------------------------------

class TaskListResult(BaseModel):
    items: list["TaskRead"]
    total: int


class BatchDeleteRequest(BaseModel):
    ids: list[uuid.UUID] = Field(default_factory=list)


class BatchDeleteResult(BaseModel):
    deleted_count: int


class ValidationResult(BaseModel):
    ok: bool
    issues: list[str] = Field(default_factory=list)
