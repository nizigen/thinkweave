"""MCP客户端管理器 — 管理所有MCP服务器连接（stub实现）

注意：完整的MCP协议集成需要 mcp SDK。
当前为 stub 实现，定义接口和数据流，待MCP SDK引入后补全连接逻辑。
实际的工具发现和调用通过 LLMClient.chat_with_tools() 的 function calling 驱动。
"""

from __future__ import annotations

from app.mcp.config import MCPServerConfig, load_mcp_config
from app.mcp.registry import MCPToolRegistry, ToolDefinition
from app.utils.logger import logger


class MCPClientManager:
    """管理所有MCP服务器连接"""

    def __init__(self, config_path: str | None = None) -> None:
        self._configs: dict[str, MCPServerConfig] = {}
        self._connected: set[str] = set()
        self._config_path = config_path
        self.registry = MCPToolRegistry()

    async def start(self) -> None:
        """启动时加载配置并连接所有MCP服务器"""
        self._configs = load_mcp_config(self._config_path)

        for name, config in self._configs.items():
            try:
                await self._connect_server(name, config)
            except Exception as e:
                logger.warning(f"Failed to connect MCP server '{name}': {e}")

        logger.info(
            f"MCP client started: {len(self._connected)}/{len(self._configs)} "
            f"servers connected, {self.registry.count} tools available"
        )

    async def stop(self) -> None:
        """关闭所有MCP服务器连接"""
        for name in list(self._connected):
            await self._disconnect_server(name)
        logger.info("MCP client stopped")

    async def _connect_server(
        self, name: str, config: MCPServerConfig
    ) -> None:
        """
        连接单个MCP服务器并发现其工具。

        TODO: 使用 mcp SDK 启动子进程并通过 stdio 通信。
        当前为 stub，仅标记为已连接。
        """
        logger.info(
            f"Connecting MCP server: {name} ({config.command} {config.args})"
        )
        self._connected.add(name)

    async def _disconnect_server(self, name: str) -> None:
        """断开单个MCP服务器连接"""
        self._connected.discard(name)
        self.registry.unregister_server(name)
        logger.info(f"Disconnected MCP server: {name}")

    async def list_tools(self) -> list[ToolDefinition]:
        """汇总所有已连接服务器提供的工具"""
        return self.registry.list_tools()

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """
        调用指定MCP工具并返回结果。

        TODO: 通过 mcp SDK 发送 tools/call 请求到对应服务器。
        TODO: 在发送前，验证 arguments 是否符合 tool.input_schema。
        当前为 stub，返回提示信息。
        """
        tool = self.registry.get(tool_name)
        if not tool:
            raise ValueError(f"Unknown tool: {tool_name}")

        logger.bind(tool=tool_name, server=tool.server_name).info(
            "Calling MCP tool"
        )
        # Stub: 实际调用待MCP SDK集成
        return f"[MCP stub] Tool '{tool_name}' called with {arguments}"

    @property
    def connected_servers(self) -> set[str]:
        return set(self._connected)
