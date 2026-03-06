"""Task Pydantic Schema"""

import uuid
from datetime import datetime

from pydantic import BaseModel


class TaskCreate(BaseModel):
    title: str
    mode: str = "report"
    depth: str = "standard"
    target_words: int = 10000


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
