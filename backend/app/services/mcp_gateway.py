"""Lightweight MCP gateway for role-scoped tool exposure and execution."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.config import settings
from app.services.mcp_registry import MCPServerConfig, get_mcp_config_stamp, load_mcp_servers


def _contains_token(values: list[str], token: str) -> bool:
    token_l = token.lower()
    return any(token_l in value.lower() for value in values)


def _is_role_allowed(role: str | None) -> bool:
    role_name = str(role or "").strip().lower()
    if not role_name:
        return False
    return role_name in settings.mcp_role_allowlist


def _safe_relative(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _detect_tool_names(server: MCPServerConfig) -> list[str]:
    fields = [server.name, server.command, server.url, server.description, *server.args]
    names: list[str] = []
    if _contains_token(fields, "mcp-server-time") or server.name.lower().endswith("time"):
        names.append("mcp.time.now")
    if _contains_token(fields, "mcp-server-fetch") or server.name.lower().endswith("fetch"):
        names.append("mcp.fetch.url")
    if _contains_token(fields, "mcp-server-filesystem") or "filesystem" in server.name.lower():
        names.append("mcp.fs.read_text")
    return names


def _tool_schema(tool_name: str, *, description: str) -> dict[str, Any]:
    if tool_name == "mcp.time.now":
        params = {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone, e.g. Asia/Shanghai",
                }
            },
            "additionalProperties": False,
        }
    elif tool_name == "mcp.fetch.url":
        params = {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "HTTP(S) URL to fetch"},
                "max_chars": {"type": "integer", "minimum": 200, "maximum": 50000},
            },
            "required": ["url"],
            "additionalProperties": False,
        }
    else:
        params = {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "head": {"type": "integer", "minimum": 1, "maximum": 5000},
                "tail": {"type": "integer", "minimum": 1, "maximum": 5000},
            },
            "required": ["path"],
            "additionalProperties": False,
        }
    return {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": description,
            "parameters": params,
        },
    }


class MCPGateway:
    """File-configured tool gateway with mtime-based cache invalidation."""

    def __init__(self) -> None:
        self._cached_tools: list[dict[str, Any]] = []
        self._cached_stamp: str = ""
        self._servers_by_tool: dict[str, str] = {}

    def _reload_if_needed(self) -> None:
        stamp = get_mcp_config_stamp()
        if self._cached_tools and stamp == self._cached_stamp:
            return

        tools: list[dict[str, Any]] = []
        servers_by_tool: dict[str, str] = {}
        for server in load_mcp_servers():
            if not server.enabled:
                continue
            for tool_name in _detect_tool_names(server):
                servers_by_tool[tool_name] = server.name
                tools.append(
                    _tool_schema(
                        tool_name,
                        description=server.description or f"MCP tool from {server.name}",
                    )
                )

        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for tool in tools:
            name = str(tool["function"]["name"])
            if name in seen:
                continue
            seen.add(name)
            deduped.append(tool)

        self._cached_tools = deduped
        self._servers_by_tool = servers_by_tool
        self._cached_stamp = stamp

    async def get_cached_mcp_tools(self, *, role: str | None) -> list[dict[str, Any]]:
        if not settings.enable_mcp_gateway:
            return []
        if not _is_role_allowed(role):
            return []
        self._reload_if_needed()
        return [json.loads(json.dumps(item)) for item in self._cached_tools]

    async def invoke_tool(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any] | None,
        role: str | None,
    ) -> dict[str, Any]:
        if not settings.enable_mcp_gateway:
            raise ValueError("MCP gateway is disabled")
        if not settings.enable_mcp_tool_execution:
            raise ValueError("MCP tool execution is disabled")
        if not _is_role_allowed(role):
            raise ValueError(f"role is not allowed to execute MCP tools: {role!r}")

        args = dict(arguments or {})
        self._reload_if_needed()

        if tool_name == "mcp.time.now":
            tz_name = str(args.get("timezone", "") or "").strip()
            if tz_name:
                now = datetime.now(ZoneInfo(tz_name))
            else:
                now = datetime.now(timezone.utc)
            return {
                "tool_name": tool_name,
                "server_name": self._servers_by_tool.get(tool_name, ""),
                "timezone": tz_name or "UTC",
                "iso_time": now.isoformat(),
            }

        if tool_name == "mcp.fetch.url":
            url = str(args.get("url", "") or "").strip()
            if not url.startswith(("http://", "https://")):
                raise ValueError("url must start with http:// or https://")
            timeout = max(5, int(settings.mcp_tool_timeout_seconds))
            limit = int(args.get("max_chars") or settings.mcp_fetch_max_chars or 8000)
            limit = max(200, min(limit, 50000))
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
            body = response.text
            return {
                "tool_name": tool_name,
                "server_name": self._servers_by_tool.get(tool_name, ""),
                "url": url,
                "status_code": response.status_code,
                "content": body[:limit],
                "truncated": len(body) > limit,
            }

        if tool_name == "mcp.fs.read_text":
            raw_path = str(args.get("path", "") or "").strip()
            if not raw_path:
                raise ValueError("path is required")
            roots = [Path(item) for item in settings.mcp_filesystem_root_list]
            if not roots:
                raise ValueError("MCP_FILESYSTEM_ROOTS is empty")
            target = Path(raw_path).expanduser().resolve()
            if not any(_safe_relative(target, root) for root in roots):
                raise ValueError("path is outside MCP filesystem roots")
            content = target.read_text(encoding="utf-8", errors="replace")
            head = args.get("head")
            tail = args.get("tail")
            lines = content.splitlines()
            if head is not None:
                slice_count = max(1, min(int(head), 5000))
                lines = lines[:slice_count]
            if tail is not None:
                slice_count = max(1, min(int(tail), 5000))
                lines = lines[-slice_count:]
            return {
                "tool_name": tool_name,
                "server_name": self._servers_by_tool.get(tool_name, ""),
                "path": str(target),
                "content": "\n".join(lines),
            }

        raise ValueError(f"unsupported MCP tool: {tool_name}")


mcp_gateway = MCPGateway()
