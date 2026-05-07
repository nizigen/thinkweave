"""Manager Agent — Layer 1 管理层

单一基类，通过 role 配置区分职责：
  - strategy: 策略规划（任务优先级、资源分配建议）
  - coordinator: 协调调度（监控执行层进度、处理阻塞）
  - quality: 质量控制（审查结果质量、决定是否需要重做）

Manager 接收来自 Orchestrator 或调度器的指令，
协调 Layer 2 执行层 Agent 的工作。
"""

from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.runtime_config import resolve_llm_call_params
from app.skills.loader import SkillLoader
from app.utils.logger import logger


# Manager 角色 → 行为描述
_MANAGER_ROLE_PROMPTS = {
    "strategy": (
        "你是策略规划管理者。分析任务需求，制定执行策略，"
        "确定子任务优先级和资源分配方案。"
    ),
    "coordinator": (
        "你是协调调度管理者。监控执行层Agent的工作进度，"
        "处理阻塞和依赖关系，确保任务按计划推进。"
    ),
    "quality": (
        "你是质量控制管理者。审查执行层产出的内容质量，"
        "决定是否需要返工，汇总质量报告。"
    ),
}


class ManagerAgent(BaseAgent):
    """Layer 1 管理 Agent — 通过 manager_role 区分职责

    manager_role: "strategy" | "coordinator" | "quality"
    """

    def __init__(self, *, manager_role: str = "coordinator", **kwargs: Any) -> None:
        super().__init__(role="manager", layer=1, **kwargs)
        if manager_role not in _MANAGER_ROLE_PROMPTS:
            raise ValueError(
                f"Invalid manager_role: {manager_role!r}, "
                f"must be one of {sorted(_MANAGER_ROLE_PROMPTS)}"
            )
        self.manager_role = manager_role
        self._skill_loader = SkillLoader()

    async def handle_task(self, ctx: dict[str, Any]) -> str:
        """处理管理层任务 — 根据 manager_role 执行不同逻辑。

        ctx 期望包含：
          - task_id: 任务 ID
          - payload.instruction: 管理指令
          - payload.context: 相关上下文信息
        """
        payload = ctx.get("payload", {})
        instruction = payload.get("instruction", "")
        context_info = payload.get("context", "")
        task_id = ctx.get("task_id", "")

        log = logger.bind(
            task_id=task_id,
            agent_id=str(self.agent_id),
            manager_role=self.manager_role,
        )

        log.info("processing manager task: {}", self.manager_role)

        system_prompt = _MANAGER_ROLE_PROMPTS[self.manager_role]
        skill_instructions = self._build_skill_instructions(payload)
        if skill_instructions:
            system_prompt += f"\n\n## Skill Constraints\n{skill_instructions}"

        messages = [
            {"role": "system", "content": system_prompt},
        ]
        if context_info:
            messages.append({"role": "user", "content": f"当前上下文：\n{context_info}"})
        messages.append({"role": "user", "content": instruction or ctx.get("title", "")})

        llm_params = resolve_llm_call_params(ctx)
        try:
            result = await self.llm_client.chat(
                messages=messages,
                role="manager",
                model=llm_params.get("model"),
                max_tokens=llm_params.get("max_tokens"),
                temperature=float(llm_params.get("temperature", 0.3)),
                max_retries=llm_params.get("max_retries"),
                fallback_models=llm_params.get("fallback_models"),
            )
        except TypeError:
            # Backward-compat path for older mocks without retry/fallback kwargs.
            result = await self.llm_client.chat(
                messages=messages,
                role="manager",
                model=llm_params.get("model"),
                max_tokens=llm_params.get("max_tokens"),
                temperature=float(llm_params.get("temperature", 0.3)),
            )

        log.info("manager task completed")
        return result

    def _build_skill_instructions(self, payload: dict[str, Any]) -> str:
        allowlist = payload.get("skill_allowlist", [])
        if not isinstance(allowlist, list) or not allowlist:
            cfg = payload.get("agent_config", {})
            if isinstance(cfg, dict):
                allowlist = cfg.get("skill_allowlist", [])
        if not isinstance(allowlist, list) or not allowlist:
            return ""

        self._skill_loader.reload()
        snippets: list[str] = []
        for name in allowlist:
            skill = self._skill_loader.get(str(name))
            if skill is None:
                continue
            snippets.append(f"### {skill.name}\n{skill.content}")
        return "\n\n".join(snippets)
