"""Writer runtime budget pool (concurrency + RPM + TPM)."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable


WINDOW_SECONDS = 60.0


@dataclass
class WriterLease:
    node_id: str
    estimated_tokens: int
    acquired_at: float


class WriterPool:
    """Controls writer slots and rolling request/token budgets."""

    def __init__(
        self,
        *,
        max_concurrent_writers: int,
        max_tokens_per_minute: int,
        max_requests_per_minute: int,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._max_concurrent_writers = max(1, int(max_concurrent_writers))
        self._max_tokens_per_minute = max(1, int(max_tokens_per_minute))
        self._max_requests_per_minute = max(1, int(max_requests_per_minute))
        self._clock = clock or time.monotonic
        self._leases: dict[str, WriterLease] = {}
        self._request_events: deque[float] = deque()
        self._token_events: deque[tuple[float, int]] = deque()

    def _prune(self, now: float) -> None:
        cutoff = now - WINDOW_SECONDS
        while self._request_events and self._request_events[0] <= cutoff:
            self._request_events.popleft()
        while self._token_events and self._token_events[0][0] <= cutoff:
            self._token_events.popleft()

    def _usage(self, now: float) -> tuple[int, int]:
        self._prune(now)
        requests_used = len(self._request_events)
        tokens_used = sum(tokens for _, tokens in self._token_events)
        return requests_used, tokens_used

    def can_acquire(self, *, estimated_tokens: int = 0) -> tuple[bool, str]:
        now = self._clock()
        requests_used, tokens_used = self._usage(now)
        token_need = max(0, int(estimated_tokens))

        if len(self._leases) >= self._max_concurrent_writers:
            return False, "concurrency_exceeded"
        if requests_used + 1 > self._max_requests_per_minute:
            return False, "request_budget_exceeded"
        if tokens_used + token_need > self._max_tokens_per_minute:
            return False, "token_budget_exceeded"
        return True, "ok"

    def acquire(self, *, node_id: str, estimated_tokens: int = 0) -> tuple[bool, str]:
        key = str(node_id)
        if key in self._leases:
            return True, "already_acquired"

        ok, reason = self.can_acquire(estimated_tokens=estimated_tokens)
        if not ok:
            return False, reason

        now = self._clock()
        token_need = max(0, int(estimated_tokens))
        self._request_events.append(now)
        self._token_events.append((now, token_need))
        self._leases[key] = WriterLease(
            node_id=key,
            estimated_tokens=token_need,
            acquired_at=now,
        )
        return True, "acquired"

    async def acquire_wait(
        self,
        *,
        node_id: str,
        estimated_tokens: int = 0,
        timeout_seconds: float = 5.0,
        poll_interval: float = 0.2,
    ) -> tuple[bool, str]:
        deadline = self._clock() + max(0.1, float(timeout_seconds))
        while self._clock() < deadline:
            ok, reason = self.acquire(node_id=node_id, estimated_tokens=estimated_tokens)
            if ok:
                return True, reason
            await asyncio.sleep(max(0.05, float(poll_interval)))
        return False, "acquire_timeout"

    def release(self, *, node_id: str) -> bool:
        key = str(node_id)
        return self._leases.pop(key, None) is not None

    def status(self) -> dict[str, Any]:
        now = self._clock()
        requests_used, tokens_used = self._usage(now)
        return {
            "active_leases": len(self._leases),
            "requests_used": requests_used,
            "tokens_used": tokens_used,
            "max_concurrent_writers": self._max_concurrent_writers,
            "max_tokens_per_minute": self._max_tokens_per_minute,
            "max_requests_per_minute": self._max_requests_per_minute,
        }

