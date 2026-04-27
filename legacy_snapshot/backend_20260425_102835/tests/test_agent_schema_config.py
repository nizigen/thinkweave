"""Schema-level tests for agent_config validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.agent import AgentConfig, AgentCreate


def test_agent_config_defaults():
    cfg = AgentConfig()
    assert cfg.temperature == 0.3
    assert cfg.max_retries == 3
    assert cfg.max_tool_iterations == 1
    assert cfg.fallback_models == []


def test_agent_config_rejects_invalid_temperature():
    with pytest.raises(ValidationError):
        AgentConfig(temperature=2.5)


def test_agent_create_accepts_agent_config():
    agent = AgentCreate(
        name="writer-1",
        role="writer",
        layer=2,
        agent_config=AgentConfig(
            goal="Produce low-overlap chapters",
            max_tool_iterations=2,
        ),
    )
    assert agent.agent_config is not None
    assert agent.agent_config.max_tool_iterations == 2
