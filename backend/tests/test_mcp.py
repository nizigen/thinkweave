"""Tests for MCP module — config, registry, client."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.mcp.transport import MCPTransport
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

    def test_load_with_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tavily-test-key")
        config_file = tmp_path / "mcp_servers.json"
        config_file.write_text(json.dumps({
            "servers": {
                "tavily": {
                    "command": "npx",
                    "args": ["-y", "tavily-mcp@latest"],
                    "env": {"TAVILY_API_KEY": "$TAVILY_API_KEY"},
                }
            }
        }), encoding="utf-8")

        configs = load_mcp_config(config_file)
        assert dict(configs["tavily"].env) == {"TAVILY_API_KEY": "tavily-test-key"}

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

        transport = _FakeTransport(
            tools=[
                ToolDefinition(
                    name="web_fetch",
                    description="Fetch a web page",
                    input_schema={"type": "object", "properties": {"url": {"type": "string"}}},
                    server_name="web_search",
                )
            ]
        )
        client = MCPClientManager(
            config_path=str(config_file),
            transport_factory=lambda _name, _cfg: transport,
        )
        await client.start()
        assert "web_search" in client.connected_servers
        assert transport.connected
        assert client.registry.get("web_fetch") is not None

    @pytest.mark.asyncio
    async def test_stop(self, tmp_path: Path):
        config_file = tmp_path / "mcp_servers.json"
        config_file.write_text(json.dumps({
            "servers": {"s1": {"command": "uvx"}}
        }), encoding="utf-8")

        transport = _FakeTransport()
        client = MCPClientManager(
            config_path=str(config_file),
            transport_factory=lambda _name, _cfg: transport,
        )
        await client.start()
        await client.stop()
        assert len(client.connected_servers) == 0
        assert transport.closed is True

    @pytest.mark.asyncio
    async def test_call_unknown_tool(self):
        client = MCPClientManager()
        with pytest.raises(ValueError, match="Unknown tool"):
            await client.call_tool("nonexistent", {})

    @pytest.mark.asyncio
    async def test_call_registered_tool_routes_to_server(self):
        client = MCPClientManager()
        transport = _FakeTransport(
            tools=[ToolDefinition(name="test_tool", server_name="s1")],
            tool_results={"test_tool": "tool ok"},
        )
        client.registry.register(ToolDefinition(name="test_tool", server_name="s1"))
        client._transports["s1"] = transport
        result = await client.call_tool("test_tool", {"key": "value"})
        assert result == "tool ok"
        assert transport.calls == [("test_tool", {"key": "value"})]

    @pytest.mark.asyncio
    async def test_start_continues_when_one_server_fails(self, tmp_path: Path):
        config_file = tmp_path / "mcp_servers.json"
        config_file.write_text(json.dumps({
            "servers": {
                "ok": {"command": "uvx"},
                "bad": {"command": "uvx"},
            }
        }), encoding="utf-8")

        def factory(name: str, _cfg: MCPServerConfig) -> MCPTransport:
            if name == "bad":
                return _FakeTransport(connect_error=RuntimeError("boom"))
            return _FakeTransport(
                tools=[ToolDefinition(name="ok_tool", server_name="ok")]
            )

        client = MCPClientManager(
            config_path=str(config_file),
            transport_factory=factory,
        )
        await client.start()

        assert client.connected_servers == {"ok"}
        assert client.registry.get("ok_tool") is not None

    @pytest.mark.asyncio
    async def test_sdk_transport_connects_and_calls_tool(self, tmp_path: Path):
        server_script = tmp_path / "fake_mcp_server.py"
        server_script.write_text(
            "\n".join(
                [
                    "from mcp.server.fastmcp import FastMCP",
                    "",
                    "server = FastMCP('test-server')",
                    "",
                    "@server.tool()",
                    "def ping(name: str) -> str:",
                    "    return f'pong:{name}'",
                    "",
                    "server.run()",
                ]
            ),
            encoding="utf-8",
        )
        config_file = tmp_path / "mcp_servers.json"
        config_file.write_text(
            json.dumps(
                {
                    "servers": {
                        "local": {
                            "command": "python",
                            "args": [str(server_script)],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        client = MCPClientManager(config_path=str(config_file))
        await client.start()
        try:
            assert "local" in client.connected_servers
            assert client.registry.get("ping") is not None
            result = await client.call_tool("ping", {"name": "codex"})
            assert result == "pong:codex"
        finally:
            await client.stop()


class _FakeTransport:
    def __init__(
        self,
        *,
        tools: list[ToolDefinition] | None = None,
        tool_results: dict[str, str] | None = None,
        connect_error: Exception | None = None,
    ) -> None:
        self._tools = tools or []
        self._tool_results = tool_results or {}
        self._connect_error = connect_error
        self.connected = False
        self.closed = False
        self.calls: list[tuple[str, dict]] = []

    async def connect(self) -> list[ToolDefinition]:
        if self._connect_error is not None:
            raise self._connect_error
        self.connected = True
        return list(self._tools)

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        self.calls.append((tool_name, arguments))
        return self._tool_results.get(tool_name, "")

    async def close(self) -> None:
        self.closed = True
