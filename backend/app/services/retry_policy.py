"""Retry ownership and policy helpers for DAG runtime vs FSM semantic loops."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RetryScope(str, Enum):
    RUNTIME = "runtime_execution"
    SEMANTIC = "semantic_quality"


@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    next_retry_count: int
    backoff_seconds: float
    scope: RetryScope
    terminal_reason: str | None = None


class RetryPolicy:
    """Centralized retry policy with explicit ownership."""

    @staticmethod
    def runtime_backoff_seconds(retry_count: int) -> float:
        # 1, 2, 4 ... capped
        return float(min(8, max(1, 2 ** max(0, retry_count))))

    @classmethod
    def runtime_failure(
        cls,
        *,
        current_retry_count: int,
        max_retries: int = 3,
        force_terminal: bool = False,
    ) -> RetryDecision:
        if force_terminal:
            return RetryDecision(
                should_retry=False,
                next_retry_count=max_retries,
                backoff_seconds=0.0,
                scope=RetryScope.RUNTIME,
                terminal_reason="forced_terminal_runtime_failure",
            )

        next_retry_count = int(current_retry_count) + 1
        if next_retry_count >= max_retries:
            return RetryDecision(
                should_retry=False,
                next_retry_count=next_retry_count,
                backoff_seconds=0.0,
                scope=RetryScope.RUNTIME,
                terminal_reason="runtime_retry_exhausted",
            )

        return RetryDecision(
            should_retry=True,
            next_retry_count=next_retry_count,
            backoff_seconds=cls.runtime_backoff_seconds(current_retry_count),
            scope=RetryScope.RUNTIME,
            terminal_reason=None,
        )

    @staticmethod
    def semantic_retry_allowed(
        *,
        current_retry_count: int,
        max_retries: int,
    ) -> bool:
        return int(current_retry_count) < int(max_retries)
