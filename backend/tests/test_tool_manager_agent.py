from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest

from app.agents.tool_manager_agent import ToolManagerAgent
from app.services.mcp_gateway import mcp_gateway
from app.services.tool_lifecycle import tool_lifecycle_service
from tests.conftest import MockLLMClient


@pytest.fixture(autouse=True)
async def clear_tool_lifecycle_state():
    await tool_lifecycle_service.clear()
    yield
    await tool_lifecycle_service.clear()


@pytest.mark.asyncio
async def test_tool_manager_agent_register_and_get():
    agent = ToolManagerAgent(
        agent_id=uuid.uuid4(),
        name="tool-manager",
        llm_client=MockLLMClient(),
        middlewares=(),
    )

    raw = await agent.handle_task(
        {
            "task_id": "task-1",
            "node_id": "node-1",
            "payload": {
                "action": "register",
                "tool_name": "web.search",
                "metadata": {"reason": "research"},
            },
        }
    )
    created = json.loads(raw)
    assert created["tool_name"] == "web.search"
    assert created["status"] == "registered"

    fetched_raw = await agent.handle_task(
        {
            "payload": {
                "action": "get",
                "run_id": created["run_id"],
            }
        }
    )
    fetched = json.loads(fetched_raw)
    assert fetched["run_id"] == created["run_id"]
    assert fetched["task_id"] == "task-1"


@pytest.mark.asyncio
async def test_tool_manager_agent_update_and_list():
    agent = ToolManagerAgent(
        agent_id=uuid.uuid4(),
        name="tool-manager",
        llm_client=MockLLMClient(),
        middlewares=(),
    )
    created = json.loads(
        await agent.handle_task(
            {
                "payload": {
                    "action": "register",
                    "tool_name": "browser.open",
                }
            }
        )
    )

    updated = json.loads(
        await agent.handle_task(
            {
                "payload": {
                    "action": "update",
                    "run_id": created["run_id"],
                    "status": "failed",
                    "error": "network_error",
                }
            }
        )
    )
    assert updated["status"] == "failed"
    assert updated["error"] == "network_error"

    listed = json.loads(
        await agent.handle_task(
            {
                "payload": {
                    "action": "list",
                    "status": "failed",
                }
            }
        )
    )
    assert len(listed["items"]) == 1
    assert listed["items"][0]["run_id"] == created["run_id"]


@pytest.mark.asyncio
async def test_tool_manager_agent_rejects_invalid_status():
    agent = ToolManagerAgent(
        agent_id=uuid.uuid4(),
        name="tool-manager",
        llm_client=MockLLMClient(),
        middlewares=(),
    )
    created = json.loads(
        await agent.handle_task(
            {
                "payload": {
                    "action": "register",
                    "tool_name": "tool.invalid",
                }
            }
        )
    )

    with pytest.raises(ValueError, match="invalid lifecycle status"):
        await agent.handle_task(
            {
                "payload": {
                    "action": "update",
                    "run_id": created["run_id"],
                    "status": "not_a_status",
                }
            }
        )


@pytest.mark.asyncio
async def test_tool_manager_agent_rejects_invalid_action():
    agent = ToolManagerAgent(
        agent_id=uuid.uuid4(),
        name="tool-manager",
        llm_client=MockLLMClient(),
        middlewares=(),
    )

    with pytest.raises(ValueError, match="invalid lifecycle action"):
        await agent.handle_task(
            {
                "payload": {
                    "action": "unknown_action",
                }
            }
        )


@pytest.mark.asyncio
async def test_tool_manager_agent_list_tools(monkeypatch: pytest.MonkeyPatch):
    agent = ToolManagerAgent(
        agent_id=uuid.uuid4(),
        name="tool-manager",
        llm_client=MockLLMClient(),
        middlewares=(),
    )
    mocked = [{"type": "function", "function": {"name": "mcp.time.now"}}]
    monkeypatch.setattr(
        mcp_gateway,
        "get_cached_mcp_tools",
        AsyncMock(return_value=mocked),
    )

    raw = await agent.handle_task({"payload": {"action": "list_tools", "role": "researcher"}})
    data = json.loads(raw)
    assert len(data["items"]) == 1
    assert data["items"][0]["function"]["name"] == "mcp.time.now"


@pytest.mark.asyncio
async def test_tool_manager_agent_invoke_records_full_lifecycle(monkeypatch: pytest.MonkeyPatch):
    agent = ToolManagerAgent(
        agent_id=uuid.uuid4(),
        name="tool-manager",
        llm_client=MockLLMClient(),
        middlewares=(),
    )
    monkeypatch.setattr(
        mcp_gateway,
        "invoke_tool",
        AsyncMock(
            return_value={
                "tool_name": "mcp.time.now",
                "server_name": "time",
                "iso_time": "2026-05-09T00:00:00+00:00",
            }
        ),
    )

    raw = await agent.handle_task(
        {
            "task_id": "task-2",
            "node_id": "node-2",
            "payload": {
                "action": "invoke",
                "tool_name": "mcp.time.now",
                "arguments": {"timezone": "UTC"},
                "role": "researcher",
            },
        }
    )
    data = json.loads(raw)
    assert data["ok"] is True
    run_id = str(data["run_id"])
    record = await tool_lifecycle_service.get(run_id)
    assert record is not None
    statuses = [item["status"] for item in record["transitions"]]
    assert statuses == ["registered", "running", "success", "cleaned"]
