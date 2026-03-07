"""Agent Pydantic Schema"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AgentCreate(BaseModel):
    name: str
    role: str
    layer: int
    capabilities: str | None = None
    model: str = "gpt-4o"


class AgentRead(BaseModel):
    id: uuid.UUID
    name: str
    role: str
    layer: int
    capabilities: str | None
    model: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentStatusUpdate(BaseModel):
    status: Literal["idle", "busy", "offline"]
