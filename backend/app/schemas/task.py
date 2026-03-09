"""Task Pydantic Schema"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# API Schemas
# ---------------------------------------------------------------------------

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=5, max_length=500)
    mode: str = "report"
    depth: str = "standard"
    target_words: int = Field(default=10000, ge=500, le=200000)

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
    created_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class TaskNodeRead(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    title: str
    agent_role: str | None
    status: str
    depends_on: list[uuid.UUID] | None
    retry_count: int

    model_config = {"from_attributes": True}


class TaskDetailRead(TaskRead):
    nodes: list[TaskNodeRead] = []


# ---------------------------------------------------------------------------
# DAG Validation Schemas (for LLM JSON response parsing)
# ---------------------------------------------------------------------------

VALID_MODES = {"report", "novel", "custom"}
VALID_DEPTHS = {"quick", "standard", "deep"}
VALID_AGENT_ROLES = {"outline", "writer", "reviewer", "consistency"}


class DAGNodeSchema(BaseModel):
    """单个DAG节点的schema — 用于校验LLM返回的JSON"""
    id: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=1, max_length=500)
    role: str
    depends_on: list[str] = Field(default_factory=list)

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in VALID_AGENT_ROLES:
            raise ValueError(
                f"Invalid role '{v}', must be one of {VALID_AGENT_ROLES}"
            )
        return v


class DAGSchema(BaseModel):
    """DAG整体schema — 用于校验LLM返回的JSON"""
    nodes: list[DAGNodeSchema] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Input Validation Result
# ---------------------------------------------------------------------------

class ValidationResult(BaseModel):
    ok: bool
    issues: list[str] = Field(default_factory=list)
