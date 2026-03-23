"""Tests for MCP module — config, registry, client."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.mcp.config import MCPServerConfig, load_mcp_config
from app.mcp.registry import MCPToolRegistry, ToolDefinition
from app.mcp.client import MCPClientManager


# ---------------------------------------------------------------------------
# Config Tests
# ---------------------------------------------------------------------------

class TestMCPConfig:
    def test_load_valid_config(self, tmp_path: Path):
        config_file = tmp_path / "mcp_servers.json"
        config_file.write_text(json.dumps({
            "servers": {
                "web_search": {
                    "command": "uvx",
                    "args": ["mcp-server-fetch"],
                    "description": "网页抓取"
                }
            }
        }), encoding="utf-8")

        configs = load_mcp_config(config_file)
        assert "web_search" in configs
        cfg = configs["web_search"]
        assert cfg.command == "uvx"
        assert list(cfg.args) == ["mcp-server-fetch"]
        assert cfg.description == "网页抓取"

    def test_load_with_env(self, tmp_path: Path):
        config_file = tmp_path / "mcp_servers.json"
        config_file.write_text(json.dumps({
            "servers": {
                "brave": {
                    "command": "npx",
                    "args": ["-y", "@anthropic-ai/mcp-server-brave-search"],
                    "env": {"BRAVE_API_KEY": "$BRAVE_API_KEY"},
                }
            }
        }), encoding="utf-8")

        configs = load_mcp_config(config_file)
        assert dict(configs["brave"].env) == {"BRAVE_API_KEY": "$BRAVE_API_KEY"}

    def test_load_nonexistent_file(self, tmp_path: Path):
        configs = load_mcp_config(tmp_path / "nonexistent.json")
        assert configs == {}

    def test_load_invalid_json(self, tmp_path: Path):
        config_file = tmp_path / "bad.json"
        config_file.write_text("not json", encoding="utf-8")
        configs = load_mcp_config(config_file)
        assert configs == {}

    def test_skip_invalid_server(self, tmp_path: Path):
        config_file = tmp_path / "mcp_servers.json"
        config_file.write_text(json.dumps({
            "servers": {
                "good": {"command": "uvx", "args": []},
                "bad": {"no_command_key": True},
            }
        }), encoding="utf-8")

        configs = load_mcp_config(config_file)
        assert "good" in configs
        assert "bad" not in configs

    def test_server_config_frozen(self):
        cfg = MCPServerConfig(name="test", command="uvx")
        with pytest.raises(AttributeError):
            cfg.name = "changed"


# ---------------------------------------------------------------------------
# Registry Tests
# ---------------------------------------------------------------------------

class TestMCPToolRegistry:
    def test_register_and_list(self):
        registry = MCPToolRegistry()
        tool = ToolDefinition(
            name="web_fetch",
            description="Fetch a web page",
            input_schema={"type": "object", "properties": {"url": {"type": "string"}}},
            server_name="web_search",
        )
        registry.register(tool)
        assert registry.count == 1
        assert registry.get("web_fetch") is not None

    def test_register_batch(self):
        registry = MCPToolRegistry()
        tools = [
            ToolDefinition(name="t1", server_name="s1"),
            ToolDefinition(name="t2", server_name="s1"),
        ]
        registry.register_batch(tools)
        assert registry.count == 2

    def test_unregister_server(self):
        registry = MCPToolRegistry()
        registry.register(ToolDefinition(name="t1", server_name="s1"))
        registry.register(ToolDefinition(name="t2", server_name="s2"))
        registry.unregister_server("s1")
        assert registry.count == 1
        assert registry.get("t1") is None
        assert registry.get("t2") is not None

    def test_list_specific_tools(self):
        registry = MCPToolRegistry()
        registry.register(ToolDefinition(name="t1", server_name="s1"))
        registry.register(ToolDefinition(name="t2", server_name="s1"))
        registry.register(ToolDefinition(name="t3", server_name="s1"))

        result = registry.list_tools(["t1", "t3"])
        assert len(result) == 2

    def test_list_missing_tool_skipped(self):
        registry = MCPToolRegistry()
        registry.register(ToolDefinition(name="t1", server_name="s1"))
        result = registry.list_tools(["t1", "nonexistent"])
        assert len(result) == 1

    def test_to_openai_tools(self):
        registry = MCPToolRegistry()
        registry.register(ToolDefinition(
            name="web_fetch",
            description="Fetch a web page",
            input_schema={
                "type": "object",
                "properties": {"url": {"type": "string"}},
            },
            server_name="web_search",
        ))

        tools = registry.to_openai_tools()
        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "web_fetch"
        assert tools[0]["function"]["description"] == "Fetch a web page"
        assert "url" in tools[0]["function"]["parameters"]["properties"]

    def test_to_openai_tools_subset(self):
        registry = MCPToolRegistry()
        registry.register(ToolDefinition(name="t1", server_name="s1"))
        registry.register(ToolDefinition(name="t2", server_name="s1"))

        tools = registry.to_openai_tools(["t1"])
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "t1"

    def test_to_openai_tools_empty_schema(self):
        registry = MCPToolRegistry()
        registry.register(ToolDefinition(name="t1", server_name="s1"))
        tools = registry.to_openai_tools()
        assert tools[0]["function"]["parameters"] == {"type": "object", "properties": {}}


# ---------------------------------------------------------------------------
# Client Tests
# ---------------------------------------------------------------------------

class TestMCPClientManager:
    @pytest.mark.asyncio
    async def test_start_no_config(self, tmp_path: Path):
        config_path = tmp_path / "nonexistent.json"
        client = MCPClientManager(config_path=str(config_path))
        await client.start()
        assert len(client.connected_servers) == 0

    @pytest.mark.asyncio
    async def test_start_with_config(self, tmp_path: Path):
        config_file = tmp_path / "mcp_servers.json"
        config_file.write_text(json.dumps({
            "servers": {
                "web_search": {"command": "uvx", "args": ["mcp-server-fetch"]}
            }
        }), encoding="utf-8")

        client = MCPClientManager(config_path=str(config_file))
        await client.start()
        assert "web_search" in client.connected_servers

    @pytest.mark.asyncio
    async def test_stop(self, tmp_path: Path):
        config_file = tmp_path / "mcp_servers.json"
        config_file.write_text(json.dumps({
            "servers": {"s1": {"command": "test"}}
        }), encoding="utf-8")

        client = MCPClientManager(config_path=str(config_file))
        await client.start()
        await client.stop()
        assert len(client.connected_servers) == 0

    @pytest.mark.asyncio
    async def test_call_unknown_tool(self):
        client = MCPClientManager()
        with pytest.raises(ValueError, match="Unknown tool"):
            await client.call_tool("nonexistent", {})

    @pytest.mark.asyncio
    async def test_call_registered_tool(self):
        client = MCPClientManager()
        client.registry.register(ToolDefinition(
            name="test_tool", server_name="s1"
        ))
        result = await client.call_tool("test_tool", {"key": "value"})
        assert "test_tool" in result
