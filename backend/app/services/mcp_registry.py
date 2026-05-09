"""MCP server registry loader with simple config compatibility."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    enabled: bool
    server_type: str
    command: str
    args: list[str]
    env: dict[str, str]
    url: str
    description: str


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_mcp_config_path() -> Path:
    raw = str(settings.mcp_server_config_path or "").strip()
    if not raw:
        return _backend_root() / "mcp_servers.json"
    path = Path(raw)
    if path.is_absolute():
        return path
    return _backend_root() / path


def get_mcp_config_mtime() -> float:
    path = resolve_mcp_config_path()
    if not path.exists():
        return 0.0
    return path.stat().st_mtime


def get_mcp_config_stamp() -> str:
    path = resolve_mcp_config_path()
    if not path.exists():
        return "missing"
    stat = path.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def _normalize_server_map(raw: dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw.get("mcpServers"), dict):
        return raw["mcpServers"]
    if isinstance(raw.get("servers"), dict):
        return raw["servers"]
    return {}


def _resolve_env_vars(source: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in source.items():
        token = str(value or "")
        if token.startswith("$") and len(token) > 1:
            out[str(key)] = str(os.getenv(token[1:], "") or "")
        else:
            out[str(key)] = token
    return out


def load_mcp_servers() -> list[MCPServerConfig]:
    path = resolve_mcp_config_path()
    if not path.exists():
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []

    servers: list[MCPServerConfig] = []
    for name, raw in _normalize_server_map(payload).items():
        if not isinstance(raw, dict):
            continue
        server_type = str(raw.get("type", "stdio") or "stdio").strip().lower()
        command = str(raw.get("command", "") or "").strip()
        url = str(raw.get("url", "") or "").strip()
        args = [str(item) for item in raw.get("args", []) if str(item).strip()]
        env_raw = raw.get("env", {})
        env = _resolve_env_vars(env_raw) if isinstance(env_raw, dict) else {}
        enabled = bool(raw.get("enabled", True))
        description = str(raw.get("description", "") or "")
        servers.append(
            MCPServerConfig(
                name=str(name),
                enabled=enabled,
                server_type=server_type,
                command=command,
                args=args,
                env=env,
                url=url,
                description=description,
            )
        )
    return servers
