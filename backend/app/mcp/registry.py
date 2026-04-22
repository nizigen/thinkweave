"""MCP工具注册表 — 汇总所有已连接MCP服务器的工具列表，转OpenAI tools格式"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolDefinition:
    """MCP工具定义"""
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    server_name: str = ""   # 所属MCP服务器


class MCPToolRegistry:
    """将MCP工具转换为OpenAI function calling格式"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """注册一个工具"""
        self._tools[tool.name] = tool

    def register_batch(self, tools: list[ToolDefinition]) -> None:
        """批量注册工具"""
        for tool in tools:
            self._tools[tool.name] = tool

    def unregister_server(self, server_name: str) -> None:
        """移除指定服务器的所有工具"""
        self._tools = {
            name: tool
            for name, tool in self._tools.items()
            if tool.server_name != server_name
        }

    def get(self, name: str) -> ToolDefinition | None:
        """按名称获取工具"""
        return self._tools.get(name)

    def list_tools(self, names: list[str] | None = None) -> list[ToolDefinition]:
        """列出所有或指定名称的工具"""
        if names is None:
            return list(self._tools.values())
        return [self._tools[n] for n in names if n in self._tools]

    def to_openai_tools(self, tool_names: list[str] | None = None) -> list[dict]:
        """
        将MCP工具转为OpenAI function calling tools schema。

        Args:
            tool_names: 指定工具名列表，None表示全部

        Returns:
            OpenAI tools 格式的列表
        """
        tools = self.list_tools(tool_names)
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema or {"type": "object", "properties": {}},
                },
            }
            for tool in tools
        ]

    @property
    def count(self) -> int:
        return len(self._tools)
