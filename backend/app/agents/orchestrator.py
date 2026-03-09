"""Orchestrator Agent — Layer 0 编排层

职责：
  1. 接收用户任务
  2. 调用 task_decomposer 将任务分解为 DAG
  3. 持久化 DAG 节点到数据库
  4. 启动 DAG 调度器驱动执行

Orchestrator 是整个系统的入口 Agent，由 Task API 触发。
"""

from __future__ import annotations

import uuid
from typing import Any

from app.agents.base_agent import BaseAgent
from app.services.task_decomposer import decompose_task
from app.utils.logger import logger
from app.utils.prompt_loader import PromptLoader


class OrchestratorAgent(BaseAgent):
    """Layer 0 编排 Agent — 任务分解 + DAG 生成"""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(role="orchestrator", layer=0, **kwargs)
        self._prompt_loader = PromptLoader()

    async def handle_task(self, ctx: dict[str, Any]) -> str:
        """分解任务为 DAG 子任务图。

        ctx 期望包含：
          - task_id: 任务 ID
          - payload.title: 任务标题/描述
          - payload.mode: 写作模式 (report/novel/custom)
          - payload.depth: 研究深度 (quick/standard/deep)
          - payload.target_words: 目标字数
        """
        payload = ctx.get("payload", {})
        title = payload.get("title", ctx.get("title", ""))
        mode = payload.get("mode", "report")
        depth = payload.get("depth", "standard")
        target_words = int(payload.get("target_words", 10000))
        task_id = ctx.get("task_id", "")

        log = logger.bind(
            task_id=task_id,
            agent_id=str(self.agent_id),
            agent_role=self.role,
        )

        log.info("decomposing task: mode={}, depth={}, target_words={}", mode, depth, target_words)

        dag = await decompose_task(
            title=title,
            mode=mode,
            depth=depth,
            target_words=target_words,
            llm_client=self.llm_client,
        )

        log.info("DAG generated: {} nodes", len(dag.nodes))

        # 返回 DAG JSON 字符串供调度器使用
        return dag.model_dump_json()
