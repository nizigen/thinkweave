"""Runtime bootstrap shims for agent manager integration.

This module keeps a minimal runtime bridge so agent CRUD paths can import
runtime hooks even when a full runtime bootstrap pipeline is not present.
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import logger

_runtime_mcp_client: Any | None = None


def set_runtime_mcp_client(client: Any | None) -> None:
    """Register runtime MCP client instance for option introspection."""
    global _runtime_mcp_client
    _runtime_mcp_client = client


def get_runtime_mcp_client() -> Any | None:
    """Return runtime MCP client if bootstrap has provided one."""
    return _runtime_mcp_client


async def register_persisted_agent(agent: Any) -> None:
    """Hook invoked after persisting an agent.

    The full runtime worker registration is optional in this repository state.
    """
    logger.bind(agent_id=str(getattr(agent, "id", ""))).debug(
        "runtime registration hook not configured; skipping"
    )


async def unregister_runtime_agent(agent_id: Any) -> None:
    """Hook invoked after deleting an agent from persistence."""
    logger.bind(agent_id=str(agent_id)).debug(
        "runtime unregister hook not configured; skipping"
    )
