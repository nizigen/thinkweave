"""Typed envelope contracts for the TEA protocol."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


TEA_PROTOCOL = "tea"
DEFAULT_TEA_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class TeaEnvelope:
    """Typed stream envelope compatible with legacy Redis stream fields."""

    protocol: str = TEA_PROTOCOL
    schema_version: str = DEFAULT_TEA_SCHEMA_VERSION
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    msg_type: str = ""
    from_agent: str = ""
    to_agent: str = ""
    task_id: str = ""
    node_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    ttl: int = 60

    def to_redis(self) -> dict[str, str]:
        return {
            "protocol": self.protocol,
            "schema_version": self.schema_version,
            "msg_id": self.msg_id,
            "msg_type": self.msg_type,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "task_id": self.task_id,
            "node_id": self.node_id,
            "payload": json.dumps(self.payload, ensure_ascii=False),
            "timestamp": str(self.timestamp),
            "ttl": str(self.ttl),
        }

