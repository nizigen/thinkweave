"""Encoding/decoding helpers for TEA protocol envelopes."""

from __future__ import annotations

import json
from typing import Any

from app.protocols.tea_protocol.types import TEA_PROTOCOL, TeaEnvelope
from app.protocols.tea_protocol.versioning import check_compatibility


class TeaDecodeError(ValueError):
    """Raised when a TEA envelope exists but cannot be decoded safely."""


def build_tea_envelope(
    *,
    schema_version: str,
    msg_type: str,
    from_agent: str = "",
    to_agent: str = "",
    task_id: str = "",
    node_id: str = "",
    payload: dict[str, Any] | None = None,
    ttl: int = 60,
) -> TeaEnvelope:
    return TeaEnvelope(
        schema_version=str(schema_version or "").strip(),
        msg_type=msg_type,
        from_agent=from_agent,
        to_agent=to_agent,
        task_id=task_id,
        node_id=node_id,
        payload=payload or {},
        ttl=int(ttl),
    )


def try_decode_tea_envelope(
    data: dict[str, Any],
    *,
    supported_version: str,
) -> tuple[TeaEnvelope | None, str | None]:
    protocol = str(data.get("protocol", "") or "").strip().lower()
    if not protocol:
        return None, None
    if protocol != TEA_PROTOCOL:
        return None, f"unsupported protocol: {protocol!r}"

    schema_version = str(data.get("schema_version", "") or "").strip()
    ok, reason = check_compatibility(
        incoming_version=schema_version,
        supported_version=supported_version,
    )
    if not ok:
        return None, reason

    payload_raw = data.get("payload", "{}")
    try:
        payload = json.loads(str(payload_raw or "{}"))
    except json.JSONDecodeError as exc:
        return None, f"invalid tea payload json: {exc}"
    if not isinstance(payload, dict):
        return None, "invalid tea payload: expected object"

    try:
        timestamp = float(data.get("timestamp", "0") or 0)
    except Exception:
        timestamp = 0.0
    try:
        ttl = int(data.get("ttl", "60") or 60)
    except Exception:
        ttl = 60

    envelope = TeaEnvelope(
        protocol=TEA_PROTOCOL,
        schema_version=schema_version,
        msg_id=str(data.get("msg_id", "") or ""),
        msg_type=str(data.get("msg_type", "") or ""),
        from_agent=str(data.get("from_agent", "") or ""),
        to_agent=str(data.get("to_agent", "") or ""),
        task_id=str(data.get("task_id", "") or ""),
        node_id=str(data.get("node_id", "") or ""),
        payload=payload,
        timestamp=timestamp,
        ttl=ttl,
    )
    return envelope, None

