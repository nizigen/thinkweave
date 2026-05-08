from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services import communicator
from app.services.tool_lifecycle import tool_lifecycle_service
from app.config import settings


@pytest.fixture(autouse=True)
async def clear_tool_lifecycle_state():
    await tool_lifecycle_service.clear()
    yield
    await tool_lifecycle_service.clear()


@pytest.mark.asyncio
async def test_lifecycle_register_and_status_transitions():
    record = await tool_lifecycle_service.register(tool_name="web_search")
    await tool_lifecycle_service.mark_running(run_id=record.run_id)
    await tool_lifecycle_service.mark_success(
        run_id=record.run_id,
        metadata={"result": "ok"},
    )

    snapshot = await tool_lifecycle_service.get(record.run_id)
    assert snapshot is not None
    assert snapshot["tool_name"] == "web_search"
    assert snapshot["status"] == "success"
    statuses = [item["status"] for item in snapshot["transitions"]]
    assert statuses == ["registered", "running", "success"]


@pytest.mark.asyncio
async def test_lifecycle_emit_task_event_when_task_context_present(monkeypatch: pytest.MonkeyPatch):
    mock_send_event = AsyncMock(return_value="1-0")
    monkeypatch.setattr(communicator, "send_task_event", mock_send_event)

    record = await tool_lifecycle_service.register(
        tool_name="browser.open",
        task_id="task-1",
        node_id="node-2",
    )
    await tool_lifecycle_service.mark_running(run_id=record.run_id)

    assert mock_send_event.await_count == 2
    assert mock_send_event.await_args_list[0].kwargs["msg_type"] == "tool_lifecycle"
    assert mock_send_event.await_args_list[0].kwargs["task_id"] == "task-1"
    payload = mock_send_event.await_args_list[1].kwargs["payload"]
    assert payload["status"] == "running"


@pytest.mark.asyncio
async def test_lifecycle_list_filters_by_status():
    first = await tool_lifecycle_service.register(tool_name="tool.a")
    second = await tool_lifecycle_service.register(tool_name="tool.b")
    await tool_lifecycle_service.mark_failed(run_id=first.run_id, error="timeout")
    await tool_lifecycle_service.mark_success(run_id=second.run_id)

    failed_items = await tool_lifecycle_service.list(status="failed")
    assert len(failed_items) == 1
    assert failed_items[0]["tool_name"] == "tool.a"
    assert failed_items[0]["error"] == "timeout"


@pytest.mark.asyncio
async def test_lifecycle_prunes_oldest_records_when_over_limit():
    previous_limit = settings.tool_lifecycle_max_records
    settings.tool_lifecycle_max_records = 100
    try:
        for index in range(130):
            await tool_lifecycle_service.register(tool_name=f"tool.{index}")
        items = await tool_lifecycle_service.list()
        assert len(items) == 100
        names = {item["tool_name"] for item in items}
        assert "tool.0" not in names
        assert "tool.129" in names
    finally:
        settings.tool_lifecycle_max_records = previous_limit
