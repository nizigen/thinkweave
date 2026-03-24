"""Agent Pydantic Schema"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Runtime agent profile inspired by high-star agent frameworks."""

    goal: str | None = None
    backstory: str | None = None
    description: str | None = None
    system_message: str | None = None

    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2000, ge=1, le=32000)
    max_retries: int = Field(default=3, ge=0, le=10)
    max_tool_iterations: int = Field(default=1, ge=1, le=50)

    fallback_models: list[str] = Field(default_factory=list)
    tool_allowlist: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class AgentCreate(BaseModel):
    name: str
    role: str
    layer: int
    capabilities: str | None = None
    model: str = "gpt-4o"
    agent_config: AgentConfig | None = None


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
