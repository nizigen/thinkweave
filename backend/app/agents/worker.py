"""Worker Agent — Layer 2 通用执行层

简单 Worker：接收子任务，调用 LLM 完成，返回结果。
具体的写作/审查/一致性逻辑在 Step 4.2 的专用 Agent 中实现。

Worker 根据 ctx.agent_role 自动加载对应 Prompt 模板，
并通过 llm_client 按角色选模型。
"""

from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent
from app.utils.logger import logger
from app.utils.prompt_loader import PromptLoader


class WorkerAgent(BaseAgent):
    """Layer 2 通用执行 Agent — 调用 LLM 完成子任务"""

    def __init__(self, **kwargs: Any) -> None:
        # role 可由外部指定（writer / reviewer / outline / consistency）
        kwargs.setdefault("layer", 2)
        super().__init__(**kwargs)
        self._prompt_loader = PromptLoader()

    async def handle_task(self, ctx: dict[str, Any]) -> str:
        """调用 LLM 执行子任务。

        ctx 期望包含：
          - task_id: 任务 ID
          - node_id: 节点 ID
          - title: 子任务标题
          - agent_role: 执行角色（writer/reviewer/outline/consistency）
          - payload: 子任务详细参数
        """
        task_id = ctx.get("task_id", "")
        title = ctx.get("title", "")
        agent_role = ctx.get("agent_role", self.role)
        payload = ctx.get("payload", {})

        log = logger.bind(
            task_id=task_id,
            agent_id=str(self.agent_id),
            agent_role=agent_role,
            node_id=ctx.get("node_id", ""),
        )

        log.info("executing sub-task: {}", title)

        # 构建消息
        messages = self._build_messages(title, agent_role, payload)

        # 调用 LLM
        result = await self.llm_client.chat(
            messages=messages,
            role=agent_role,
        )

        log.info("sub-task completed, result length={}", len(result))
        return result

    def _build_messages(
        self,
        title: str,
        agent_role: str,
        payload: dict[str, Any],
    ) -> list[dict[str, str]]:
        """根据角色构建 LLM 消息序列。"""
        messages: list[dict[str, str]] = []

        # 尝试加载 system prompt
        try:
            system_prompt = self._prompt_loader.load_system(agent_role)
            messages.append({"role": "system", "content": system_prompt})
        except FileNotFoundError:
            pass

        # 构建 user 消息
        user_content = self._build_user_prompt(title, agent_role, payload)
        messages.append({"role": "user", "content": user_content})

        return messages

    def _build_user_prompt(
        self,
        title: str,
        agent_role: str,
        payload: dict[str, Any],
    ) -> str:
        """构建用户 Prompt — 尝试从模板加载，失败则使用通用格式。"""
        # 角色 → 模板 action 映射
        role_action_map = {
            "outline": "generate",
            "writer": "write_chapter",
            "reviewer": "review_chapter",
            "consistency": "check",
        }

        action = role_action_map.get(agent_role)
        if action:
            try:
                return self._prompt_loader.load(
                    agent_role,
                    action,
                    **{k: str(v) for k, v in payload.items()},
                )
            except (FileNotFoundError, KeyError):
                pass

        # 通用格式 fallback
        parts = [f"## 任务\n{title}"]
        if payload:
            details = "\n".join(f"- {k}: {v}" for k, v in payload.items())
            parts.append(f"\n## 详情\n{details}")
        return "\n".join(parts)
