"""MCP client manager for connecting servers, discovering tools, and tool calls."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.mcp.config import MCPServerConfig, load_mcp_config
from app.mcp.registry import MCPToolRegistry, ToolDefinition
from app.mcp.transport import MCPTransport, SDKMCPTransport
from app.utils.logger import logger


class MCPClientManager:
    """Manage MCP server transports and expose discovered tools."""

    def __init__(
        self,
        config_path: str | None = None,
        *,
        transport_factory: Callable[[str, MCPServerConfig], MCPTransport] | None = None,
    ) -> None:
        self._configs: dict[str, MCPServerConfig] = {}
        self._connected: set[str] = set()
        self._transports: dict[str, MCPTransport] = {}
        self._config_path = config_path
        self._transport_factory = transport_factory or SDKMCPTransport
        self.registry = MCPToolRegistry()

    async def start(self) -> None:
        """Load config and connect all servers."""
        self._configs = load_mcp_config(self._config_path)

        for name, config in self._configs.items():
            try:
                await self._connect_server(name, config)
            except Exception as exc:
                logger.warning(f"Failed to connect MCP server '{name}': {exc}")

        logger.info(
            f"MCP client started: {len(self._connected)}/{len(self._configs)} "
            f"servers connected, {self.registry.count} tools available"
        )

    async def stop(self) -> None:
        """Disconnect all servers."""
        for name in list(self._connected):
            await self._disconnect_server(name)
        logger.info("MCP client stopped")

    async def _connect_server(self, name: str, config: MCPServerConfig) -> None:
        """Connect one server and register its tools."""
        transport = self._transport_factory(name, config)
        tools = await transport.connect()
        self._transports[name] = transport
        self._connected.add(name)
        normalized_tools = [
            tool
            if tool.server_name
            else ToolDefinition(
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
                server_name=name,
            )
            for tool in tools
        ]
        self.registry.register_batch(normalized_tools)
        logger.info(f"Connected MCP server: {name}, tools={len(normalized_tools)}")

    async def _disconnect_server(self, name: str) -> None:
        """Disconnect one server transport and clear its tools."""
        transport = self._transports.pop(name, None)
        if transport is not None:
            await transport.close()
        self._connected.discard(name)
        self.registry.unregister_server(name)
        logger.info(f"Disconnected MCP server: {name}")

    async def list_tools(self) -> list[ToolDefinition]:
        """List discovered tools from all connected servers."""
        return self.registry.list_tools()

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Route tool call to its owning server transport."""
        tool = self.registry.get(tool_name)
        if not tool:
            raise ValueError(f"Unknown tool: {tool_name}")
        server_name = tool.server_name
        transport = self._transports.get(server_name)
        if transport is None:
            raise RuntimeError(f"MCP server not connected: {server_name}")
        logger.bind(tool=tool_name, server=server_name).info("Calling MCP tool")
        return await transport.call_tool(tool_name, arguments)

    @property
    def connected_servers(self) -> set[str]:
        return set(self._connected)
