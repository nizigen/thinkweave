"""MCP transport abstraction and SDK-backed implementation."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from contextlib import AsyncExitStack
from typing import Any

from app.mcp.config import MCPServerConfig
from app.mcp.registry import ToolDefinition


class MCPTransport(ABC):
    """Abstract transport interface used by MCPClientManager."""

    @abstractmethod
    async def connect(self) -> list[ToolDefinition]:
        """Connect to server and return discovered tools."""

    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Call a remote MCP tool and return stringified result."""

    @abstractmethod
    async def close(self) -> None:
        """Close underlying resources."""


class SDKMCPTransport(MCPTransport):
    """Transport powered by the Python MCP SDK over stdio."""

    def __init__(self, name: str, config: MCPServerConfig) -> None:
        self._name = name
        self._config = config
        self._stack: AsyncExitStack | None = None
        self._session: Any = None

    async def connect(self) -> list[ToolDefinition]:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ModuleNotFoundError as exc:
            raise RuntimeError("mcp sdk is not installed") from exc

        if self._session is not None:
            return []

        env = dict(self._config.env)
        server_params = StdioServerParameters(
            command=self._config.command,
            args=list(self._config.args),
            env=env or None,
        )

        stack = AsyncExitStack()
        read_stream, write_stream = await stack.enter_async_context(
            stdio_client(server_params)
        )
        session = await stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()
        tools_result = await session.list_tools()

        self._stack = stack
        self._session = session
        return self._convert_tools(tools_result)

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        if self._session is None:
            raise RuntimeError(f"MCP transport '{self._name}' is not connected")

        result = await self._session.call_tool(tool_name, arguments)
        return self._stringify_result(result)

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._session = None

    def _convert_tools(self, tools_result: Any) -> list[ToolDefinition]:
        raw_tools = getattr(tools_result, "tools", None)
        if raw_tools is None and isinstance(tools_result, list):
            raw_tools = tools_result
        if raw_tools is None:
            return []

        converted: list[ToolDefinition] = []
        for raw in raw_tools:
            name = str(getattr(raw, "name", "")).strip()
            if not name:
                continue
            converted.append(
                ToolDefinition(
                    name=name,
                    description=str(getattr(raw, "description", "") or ""),
                    input_schema=dict(getattr(raw, "inputSchema", None) or {}),
                    server_name=self._name,
                )
            )
        return converted

    def _stringify_result(self, result: Any) -> str:
        if isinstance(result, str):
            return result

        content = getattr(result, "content", None)
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    text_parts.append(text)
            if text_parts:
                return "\n".join(text_parts)

        if hasattr(result, "model_dump"):
            return json.dumps(result.model_dump(), ensure_ascii=False)
        return str(result)
