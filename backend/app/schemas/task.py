"""Task Pydantic Schema"""

import uuid
import re
from typing import Any, Literal
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Constants (must be defined before schemas that reference them)
# ---------------------------------------------------------------------------

VALID_MODES = {"report", "novel", "custom"}
VALID_DEPTHS = {"quick", "standard", "deep"}
VALID_AGENT_ROLES = {"outline", "researcher", "writer", "reviewer", "consistency"}
_MOJIBAKE_PATTERN = re.compile(r"[ÃÂâæçðï]")


def _count_cjk(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def _count_mojibake_chars(text: str) -> int:
    return len(_MOJIBAKE_PATTERN.findall(text))


def _repair_utf8_mojibake(text: str) -> str:
    source = str(text or "")
    if not source or not _MOJIBAKE_PATTERN.search(source):
        return source
    try:
        repaired = bytes((ord(ch) & 0xFF) for ch in source).decode("utf-8")
    except Exception:
        return source
    source_score = _count_cjk(source) * 3 - _count_mojibake_chars(source)
    repaired_score = _count_cjk(repaired) * 3 - _count_mojibake_chars(repaired)
    if repaired_score > source_score:
        return repaired
    return source


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

    @field_validator("title")
    @classmethod
    def validate_title_encoding_health(cls, v: str) -> str:
        title = _repair_utf8_mojibake(str(v or "")).strip()
        if not title:
            return title
        q_count = title.count("?")
        has_cjk = bool(re.search(r"[\u4e00-\u9fff]", title))
        if q_count >= 4 and not has_cjk:
            raise ValueError(
                "Title appears encoding-corrupted (contains too many '?'). "
                "Please re-enter title using UTF-8 input."
            )
        return title


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
    depends_on: list[uuid.UUID] = Field(default_factory=list)
    retry_count: int
    version: int = 0
    started_at: datetime | None
    finished_at: datetime | None
    required_capabilities: list[str] = Field(default_factory=list)
    preferred_agents: list[str] = Field(default_factory=list)
    routing_mode: Literal["auto", "capability_first", "strict_bind"] = "auto"
    routing_reason: str | None = None
    routing_status: str | None = None
    stage_code: str = "QA"
    stage_name: str | None = None

    model_config = {"from_attributes": True}


class TaskDetailRead(TaskRead):
    output_text: str | None = None
    checkpoint_data: dict[str, Any] = Field(default_factory=dict)
    nodes: list[TaskNodeRead] = Field(default_factory=list)
    blocking_reason: str | None = None
    node_status_summary: dict[str, int] = Field(default_factory=dict)
    stage_progress: dict[str, int] = Field(default_factory=dict)
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    citation_summary: dict[str, int] = Field(default_factory=dict)
    decomposition_audit_summary: dict[str, Any] = Field(default_factory=dict)


class DecompositionAuditRead(BaseModel):
    task_id: uuid.UUID
    attempt_no: int
    decomposition_input: dict[str, Any] = Field(default_factory=dict)
    raw_llm_output: dict[str, Any] | None = None
    normalized_dag: dict[str, Any] = Field(default_factory=dict)
    validation_issues: list[str] = Field(default_factory=list)
    repair_actions: list[dict[str, Any]] = Field(default_factory=list)
    decomposer_version: str
    created_at: datetime | None = None


class TaskControlSkipRequest(BaseModel):
    node_id: uuid.UUID


class TaskControlRetryRequest(BaseModel):
    node_id: uuid.UUID


class TaskControlAdminSkipRequest(BaseModel):
    node_id: uuid.UUID
    reason: str = Field(..., min_length=1, max_length=500)


class TaskControlAdminRetryRequest(BaseModel):
    node_id: uuid.UUID
    reason: str = Field(..., min_length=1, max_length=500)


class TaskControlForceTransitionRequest(BaseModel):
    to_state: str = Field(..., min_length=1, max_length=64)
    reason: str = Field(..., min_length=1, max_length=500)


class TaskControlResumeFromCheckpointRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


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
