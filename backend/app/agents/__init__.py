"""Agent 模块 — 三层 Agent 架构

Layer 0: Orchestrator (编排层) — 任务分解和全局协调
Layer 1: Manager (管理层) — 通过 role 配置区分策略/协调/质量职责
Layer 2: Worker (执行层) — 通用 LLM 子任务执行
         专用 Agent（outline/writer/reviewer/consistency）在 Step 4.2 实现
"""

from app.agents.agent_registry import AgentRegistry, agent_registry
from app.agents.base_agent import BaseAgent
from app.agents.manager import ManagerAgent
from app.agents.middleware import (
    AgentMiddleware,
    ContextSummaryMiddleware,
    DEFAULT_MIDDLEWARES,
    LoggingMiddleware,
    TimeoutMiddleware,
    TokenTrackingMiddleware,
)
from app.agents.orchestrator import OrchestratorAgent
from app.agents.worker import WorkerAgent

__all__ = [
    "AgentMiddleware",
    "AgentRegistry",
    "BaseAgent",
    "ContextSummaryMiddleware",
    "DEFAULT_MIDDLEWARES",
    "LoggingMiddleware",
    "ManagerAgent",
    "OrchestratorAgent",
    "TimeoutMiddleware",
    "TokenTrackingMiddleware",
    "WorkerAgent",
    "agent_registry",
]
