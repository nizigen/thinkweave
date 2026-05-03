"""Agent Pydantic Schema"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from app.config import settings


class AgentConfig(BaseModel):
    """Runtime agent profile inspired by high-star agent frameworks."""

    goal: str | None = None
    backstory: str | None = None
    description: str | None = None
    system_message: str | None = None

    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2000, ge=1, le=32000)
    max_retries: int = Field(default=3, ge=0, le=10)
    max_tool_iterations: int = Field(default=1, ge=1, le=50)

    fallback_models: list[str] = Field(default_factory=list)
    skill_allowlist: list[str] = Field(default_factory=list)
    tool_allowlist: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class AgentCreate(BaseModel):
    name: str
    role: str
    layer: int
    capabilities: str | None = None
    model: str | None = Field(default=settings.default_model)
    custom_model: str | None = None
    agent_config: AgentConfig | None = None

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if len(v) > 2000:
            raise ValueError("capabilities must be <= 2000 characters")
        tokens = [
            token.strip()
            for token in v.replace("\n", ",").replace(";", ",").replace("|", ",").split(",")
            if token.strip()
        ]
        for token in tokens:
            if len(token) > 64:
                raise ValueError("each capability token must be <= 64 characters")
        return v


class AgentRead(BaseModel):
    id: uuid.UUID
    name: str
    role: str
    layer: int
    capabilities: str | None
    model: str
    agent_config: AgentConfig | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentStatusUpdate(BaseModel):
    status: Literal["idle", "busy", "offline"]


class AgentHealthRead(BaseModel):
    id: uuid.UUID
    status: str
    runtime_status: str
    current_task: str = ""
    current_node: str = ""
    capabilities: str | None = None
    error_count: int = 0
    last_heartbeat: float | None = None
    heartbeat_age_seconds: float | None = None


class ModelOptionRead(BaseModel):
    value: str
    label: str
    description: str = ""
    provider: str = ""


class SkillOptionRead(BaseModel):
    name: str
    skill_type: str
    description: str = ""
    applicable_roles: list[str] = Field(default_factory=list)
    applicable_modes: list[str] = Field(default_factory=list)
    applicable_stages: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    model_preference: str | None = None
    priority: int = 100
    source_path: str = ""


class ToolOptionRead(BaseModel):
    name: str
    description: str = ""
    server_name: str = ""


class RolePresetConfigRead(BaseModel):
    skill_allowlist: list[str] = Field(default_factory=list)
    tool_allowlist: list[str] = Field(default_factory=list)
    max_tool_iterations: int = Field(default=1, ge=1, le=50)


class RolePresetRead(BaseModel):
    role: str
    layer: int
    label: str
    description: str = ""
    icon: str = ""
    default_model: str
    agent_config: RolePresetConfigRead
