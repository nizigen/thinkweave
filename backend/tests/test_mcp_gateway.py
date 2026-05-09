from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import settings
from app.services.mcp_gateway import MCPGateway


@pytest.fixture
def mcp_settings_guard():
    old_enable_gateway = settings.enable_mcp_gateway
    old_enable_exec = settings.enable_mcp_tool_execution
    old_roles = settings.mcp_enabled_roles
    old_path = settings.mcp_server_config_path
    old_roots = settings.mcp_filesystem_roots
    old_timeout = settings.mcp_tool_timeout_seconds
    old_fetch_max = settings.mcp_fetch_max_chars
    try:
        yield
    finally:
        settings.enable_mcp_gateway = old_enable_gateway
        settings.enable_mcp_tool_execution = old_enable_exec
        settings.mcp_enabled_roles = old_roles
        settings.mcp_server_config_path = old_path
        settings.mcp_filesystem_roots = old_roots
        settings.mcp_tool_timeout_seconds = old_timeout
        settings.mcp_fetch_max_chars = old_fetch_max


def _write_servers(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


@pytest.mark.asyncio
async def test_get_cached_mcp_tools_respects_role_and_config(tmp_path: Path, mcp_settings_guard):
    cfg = tmp_path / "mcp_servers.json"
    _write_servers(
        cfg,
        {
            "servers": {
                "time": {"command": "uvx", "args": ["mcp-server-time"], "enabled": True},
                "fetch": {"command": "uvx", "args": ["mcp-server-fetch"], "enabled": True},
            }
        },
    )
    settings.enable_mcp_gateway = True
    settings.enable_mcp_tool_execution = False
    settings.mcp_enabled_roles = "researcher"
    settings.mcp_server_config_path = str(cfg)

    gateway = MCPGateway()
    researcher_tools = await gateway.get_cached_mcp_tools(role="researcher")
    writer_tools = await gateway.get_cached_mcp_tools(role="writer")
    names = {item["function"]["name"] for item in researcher_tools}

    assert "mcp.time.now" in names
    assert "mcp.fetch.url" in names
    assert writer_tools == []


@pytest.mark.asyncio
async def test_get_cached_mcp_tools_reloads_after_config_change(tmp_path: Path, mcp_settings_guard):
    cfg = tmp_path / "mcp_servers.json"
    _write_servers(cfg, {"servers": {"time": {"command": "uvx", "args": ["mcp-server-time"]}}})

    settings.enable_mcp_gateway = True
    settings.mcp_enabled_roles = "researcher"
    settings.mcp_server_config_path = str(cfg)

    gateway = MCPGateway()
    first = await gateway.get_cached_mcp_tools(role="researcher")
    first_names = {item["function"]["name"] for item in first}
    assert first_names == {"mcp.time.now"}

    _write_servers(
        cfg,
        {
            "servers": {
                "time": {"command": "uvx", "args": ["mcp-server-time"]},
                "fetch": {"command": "uvx", "args": ["mcp-server-fetch"]},
            }
        },
    )
    second = await gateway.get_cached_mcp_tools(role="researcher")
    second_names = {item["function"]["name"] for item in second}
    assert "mcp.fetch.url" in second_names


@pytest.mark.asyncio
async def test_invoke_time_tool(tmp_path: Path, mcp_settings_guard):
    cfg = tmp_path / "mcp_servers.json"
    _write_servers(cfg, {"servers": {"time": {"command": "uvx", "args": ["mcp-server-time"]}}})

    settings.enable_mcp_gateway = True
    settings.enable_mcp_tool_execution = True
    settings.mcp_enabled_roles = "researcher"
    settings.mcp_server_config_path = str(cfg)

    gateway = MCPGateway()
    result = await gateway.invoke_tool(
        tool_name="mcp.time.now",
        arguments={"timezone": "UTC"},
        role="researcher",
    )
    assert result["tool_name"] == "mcp.time.now"
    assert result["timezone"] == "UTC"
    assert "iso_time" in result


@pytest.mark.asyncio
async def test_invoke_filesystem_tool_with_whitelist(tmp_path: Path, mcp_settings_guard):
    cfg = tmp_path / "mcp_servers.json"
    _write_servers(
        cfg,
        {"servers": {"fs": {"command": "uvx", "args": ["mcp-server-filesystem"]}}},
    )
    note = tmp_path / "note.txt"
    note.write_text("line1\nline2\nline3\n", encoding="utf-8")

    settings.enable_mcp_gateway = True
    settings.enable_mcp_tool_execution = True
    settings.mcp_enabled_roles = "researcher"
    settings.mcp_server_config_path = str(cfg)
    settings.mcp_filesystem_roots = str(tmp_path)

    gateway = MCPGateway()
    result = await gateway.invoke_tool(
        tool_name="mcp.fs.read_text",
        arguments={"path": str(note), "head": 2},
        role="researcher",
    )
    assert result["tool_name"] == "mcp.fs.read_text"
    assert "line1" in result["content"]
    assert "line3" not in result["content"]
