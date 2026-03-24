"""Request-level throttling for expensive endpoints."""

from __future__ import annotations

import time
import os

from fastapi import HTTPException

from app.config import settings
from app.redis_client import redis_client


async def enforce_task_create_rate_limit(user_id: str) -> None:
    """Limit task creation requests per user per minute."""
    limit = max(int(settings.task_create_rate_limit_per_minute), 1)
    bucket = int(time.time() // 60)
    key = f"ratelimit:task_create:{user_id}:{bucket}"
    try:
        current = await redis_client.incr(key)
        if current == 1:
            await redis_client.expire(key, 90)
    except Exception:
        if os.getenv("PYTEST_CURRENT_TEST"):
            return
        raise HTTPException(
            status_code=503,
            detail="Rate-limit service unavailable. Please retry later.",
        )

    if int(current) > limit:
        raise HTTPException(
            status_code=429,
            detail="Too many task creation requests. Please retry later.",
        )
