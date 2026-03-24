"""Runtime resolution helpers for agent model invocation parameters."""

from __future__ import annotations

from typing import Any


def resolve_llm_call_params(ctx: dict[str, Any]) -> dict[str, Any]:
    """Resolve per-task LLM parameters from scheduler-injected payload.

    Priority:
    1. payload.agent_config (structured overrides)
    2. payload.model (agent row model)
    3. caller defaults in llm_client role mapping
    """
    payload = ctx.get("payload", {}) or {}
    agent_config = payload.get("agent_config") or {}

    params: dict[str, Any] = {}

    model = payload.get("model")
    if isinstance(model, str) and model:
        params["model"] = model

    max_tokens = agent_config.get("max_tokens")
    if isinstance(max_tokens, int) and max_tokens > 0:
        params["max_tokens"] = max_tokens

    temperature = agent_config.get("temperature")
    if isinstance(temperature, (int, float)):
        temp = float(temperature)
        if 0.0 <= temp <= 2.0:
            params["temperature"] = temp

    max_retries = agent_config.get("max_retries")
    if isinstance(max_retries, int) and max_retries >= 0:
        params["max_retries"] = max_retries

    fallback_models = agent_config.get("fallback_models")
    if isinstance(fallback_models, list):
        normalized = [
            m.strip()
            for m in fallback_models
            if isinstance(m, str) and m.strip()
        ]
        if normalized:
            params["fallback_models"] = normalized

    return params
