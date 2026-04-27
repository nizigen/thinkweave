"""Message Pydantic Schema"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MessageRead(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID | None
    from_agent: str | None
    to_agent: str | None
    msg_type: str | None
    content: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}
