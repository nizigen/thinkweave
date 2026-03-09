"""Agent 注册表 — 维护运行时 Agent 实例索引，用于能力匹配和调度

Agent 注册 = 数据库定义 + 运行时实例化。
AgentRegistry 管理所有活跃的 Agent 协程实例。
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.agents.base_agent import BaseAgent
from app.utils.logger import logger


class AgentRegistry:
    """Agent 运行时注册表

    职责：
    1. 注册/注销 Agent 实例
    2. 按角色/层级查找 Agent
    3. 管理 Agent 协程生命周期（启动/停止）
    """

    def __init__(self) -> None:
        # {agent_id: BaseAgent}
        self._agents: dict[uuid.UUID, BaseAgent] = {}
        # {agent_id: asyncio.Task} — 运行中的协程
        self._tasks: dict[uuid.UUID, asyncio.Task[None]] = {}

    # ------------------------------------------------------------------
    # 注册 / 注销
    # ------------------------------------------------------------------

    def register(self, agent: BaseAgent) -> None:
        """注册 Agent 实例（不启动运行）。"""
        if agent.agent_id in self._agents:
            logger.warning("agent already registered: {}", agent.agent_id)
            return
        self._agents[agent.agent_id] = agent
        logger.bind(
            agent_id=str(agent.agent_id),
            agent_role=agent.role,
        ).info("agent registered: {}", agent.name)

    def unregister(self, agent_id: uuid.UUID) -> None:
        """注销 Agent 实例并停止运行。"""
        agent = self._agents.pop(agent_id, None)
        if agent:
            agent.stop()
        task = self._tasks.pop(agent_id, None)
        if task and not task.done():
            task.cancel()
        logger.bind(agent_id=str(agent_id)).info("agent unregistered")

    # ------------------------------------------------------------------
    # 启动 / 停止
    # ------------------------------------------------------------------

    async def start_agent(self, agent_id: uuid.UUID) -> None:
        """启动 Agent 运行循环（后台协程）。"""
        agent = self._agents.get(agent_id)
        if agent is None:
            raise ValueError(f"Agent not found: {agent_id}")
        if agent_id in self._tasks and not self._tasks[agent_id].done():
            logger.warning("agent already running: {}", agent_id)
            return

        task = asyncio.create_task(self._run_agent(agent))
        self._tasks[agent_id] = task

    async def start_all(self) -> None:
        """启动所有已注册的 Agent。"""
        for agent_id in self._agents:
            await self.start_agent(agent_id)

    async def stop_agent(self, agent_id: uuid.UUID) -> None:
        """停止指定 Agent。"""
        agent = self._agents.get(agent_id)
        if agent:
            agent.stop()
        task = self._tasks.get(agent_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.pop(agent_id, None)

    async def stop_all(self) -> None:
        """停止所有 Agent。"""
        for agent_id in list(self._tasks):
            await self.stop_agent(agent_id)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get(self, agent_id: uuid.UUID) -> BaseAgent | None:
        """按 ID 获取 Agent 实例。"""
        return self._agents.get(agent_id)

    def find_by_role(self, role: str) -> list[BaseAgent]:
        """按角色查找 Agent。"""
        return [a for a in self._agents.values() if a.role == role]

    def find_by_layer(self, layer: int) -> list[BaseAgent]:
        """按层级查找 Agent。"""
        return [a for a in self._agents.values() if a.layer == layer]

    def list_all(self) -> list[BaseAgent]:
        """列出所有已注册的 Agent。"""
        return list(self._agents.values())

    @property
    def count(self) -> int:
        return len(self._agents)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run_agent(self, agent: BaseAgent) -> None:
        """运行 Agent 并在结束时清理。"""
        try:
            await agent.run()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.opt(exception=True).error(
                "agent {} crashed", agent.agent_id,
            )
        finally:
            self._tasks.pop(agent.agent_id, None)


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

agent_registry = AgentRegistry()
