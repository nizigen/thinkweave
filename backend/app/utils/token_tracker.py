"""Token用量追踪 — 按task_id/agent_role聚合，用于成本监控"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UsageRecord:
    """单条聚合记录"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    call_count: int = 0

    def to_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cached_tokens": self.cached_tokens,
            "call_count": self.call_count,
        }


class TokenTracker:
    """
    按 task_id 和 agent_role 聚合 Token 用量。

    asyncio 协程环境中无需加锁（协作式调度，record() 内无 await）。
    """

    def __init__(self) -> None:
        self._by_task: dict[str, UsageRecord] = {}
        self._by_role: dict[str, UsageRecord] = {}

    def record(
        self,
        *,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0,
        task_id: str | None = None,
        role: str | None = None,
    ) -> None:
        """记录一次LLM调用的token用量"""
        total = prompt_tokens + completion_tokens

        if task_id:
            rec = self._by_task.setdefault(task_id, UsageRecord())
            rec.prompt_tokens += prompt_tokens
            rec.completion_tokens += completion_tokens
            rec.total_tokens += total
            rec.cached_tokens += cached_tokens
            rec.call_count += 1

        if role:
            rec = self._by_role.setdefault(role, UsageRecord())
            rec.prompt_tokens += prompt_tokens
            rec.completion_tokens += completion_tokens
            rec.total_tokens += total
            rec.cached_tokens += cached_tokens
            rec.call_count += 1

    def get_task_usage(self, task_id: str) -> UsageRecord:
        return self._by_task.get(task_id, UsageRecord())

    def get_role_usage(self, role: str) -> UsageRecord:
        return self._by_role.get(role, UsageRecord())

    def get_summary(self) -> dict:
        return {
            "by_task": {k: v.to_dict() for k, v in self._by_task.items()},
            "by_role": {k: v.to_dict() for k, v in self._by_role.items()},
        }

    def reset(self) -> None:
        self._by_task.clear()
        self._by_role.clear()
