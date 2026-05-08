from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.protocols.tea_protocol import (
    TeaEnvelope,
    build_tea_envelope,
    check_compatibility,
    parse_schema_version,
    try_decode_tea_envelope,
)
from app.services import communicator


def test_parse_schema_version():
    assert parse_schema_version("1.0") == (1, 0)
    assert parse_schema_version("2.7") == (2, 7)


def test_check_compatibility():
    assert check_compatibility("1.0", "1.2")[0] is True
    assert check_compatibility("1.2", "1.2")[0] is True
    assert check_compatibility("2.0", "1.9")[0] is False
    assert check_compatibility("1.3", "1.2")[0] is False


def test_try_decode_without_protocol_returns_none():
    envelope, error = try_decode_tea_envelope(
        data={"msg_type": "task_assign"},
        supported_version="1.0",
    )
    assert envelope is None
    assert error is None


def test_tea_round_trip():
    original = build_tea_envelope(
        schema_version="1.0",
        msg_type="task_assign",
        task_id="task-1",
        node_id="node-1",
        payload={"k": "v"},
    )
    data = original.to_redis()
    decoded, error = try_decode_tea_envelope(data=data, supported_version="1.0")
    assert error is None
    assert decoded is not None
    assert decoded.msg_type == "task_assign"
    assert decoded.task_id == "task-1"
    assert decoded.payload == {"k": "v"}


def test_tea_decode_rejects_newer_minor():
    original = build_tea_envelope(
        schema_version="1.3",
        msg_type="task_result",
        payload={"ok": True},
    )
    decoded, error = try_decode_tea_envelope(
        data=original.to_redis(),
        supported_version="1.2",
    )
    assert decoded is None
    assert error is not None
    assert "newer than supported" in error


@pytest.mark.asyncio
async def test_send_task_event_uses_tea_envelope_when_enabled():
    previous_enable = settings.enable_tea_protocol
    previous_version = settings.tea_protocol_version
    settings.enable_tea_protocol = True
    settings.tea_protocol_version = "1.0"
    try:
        with (
            patch("app.services.communicator.xadd", new_callable=AsyncMock, return_value="1-0") as mock_xadd,
        ):
            await communicator.send_task_event(
                task_id="t1",
                msg_type="status_update",
                payload={"status": "running"},
                node_id="n1",
                from_agent="scheduler",
            )
        envelope = mock_xadd.await_args.args[1]
        assert isinstance(envelope, TeaEnvelope)
        assert envelope.schema_version == "1.0"
    finally:
        settings.enable_tea_protocol = previous_enable
        settings.tea_protocol_version = previous_version


def test_decode_incoming_envelope_tea_path():
    previous_enable = settings.enable_tea_protocol
    previous_version = settings.tea_protocol_version
    settings.enable_tea_protocol = True
    settings.tea_protocol_version = "1.0"
    try:
        envelope = build_tea_envelope(
            schema_version="1.0",
            msg_type="task_assign",
            task_id="t1",
            node_id="n1",
            payload={"title": "x"},
        )
        decoded = communicator.decode_incoming_envelope(envelope.to_redis())
        assert isinstance(decoded, TeaEnvelope)
        assert decoded.msg_type == "task_assign"
    finally:
        settings.enable_tea_protocol = previous_enable
        settings.tea_protocol_version = previous_version


def test_decode_incoming_envelope_rejects_incompatible_tea_version():
    previous_enable = settings.enable_tea_protocol
    previous_version = settings.tea_protocol_version
    settings.enable_tea_protocol = True
    settings.tea_protocol_version = "1.0"
    try:
        envelope = build_tea_envelope(
            schema_version="2.0",
            msg_type="task_assign",
            task_id="t1",
            node_id="n1",
            payload={"title": "x"},
        )
        with pytest.raises(ValueError, match="TEA decode failed"):
            communicator.decode_incoming_envelope(envelope.to_redis())
    finally:
        settings.enable_tea_protocol = previous_enable
        settings.tea_protocol_version = previous_version
