"""MCP服务器配置加载 — 从mcp_servers.json读取"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from app.utils.logger import logger

# 允许的MCP服务器启动命令白名单
_ALLOWED_COMMANDS = frozenset({"npx", "node", "python", "python3", "uvx", "docker"})

# 禁止的危险环境变量（可注入代码执行）
_BLOCKED_ENV_VARS = frozenset({
    "LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES",
    "NODE_OPTIONS", "PYTHONSTARTUP", "PYTHONPATH",
})

# Shell元字符检测（用于参数校验）
_SHELL_META_RE = re.compile(r"[;&|`$(){}]")
_ENV_REF_RE = re.compile(r"^\$(?:\{(?P<braced>[A-Z0-9_]+)\}|(?P<bare>[A-Z0-9_]+))$")


@dataclass(frozen=True)
class MCPServerConfig:
    """单个MCP服务器的配置"""
    name: str
    command: str
    args: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    description: str = ""


def _resolve_env_value(value: object) -> str:
    if not isinstance(value, str):
        return ""
    candidate = value.strip()
    match = _ENV_REF_RE.match(candidate)
    if not match:
        return value
    env_key = match.group("braced") or match.group("bare") or ""
    return os.getenv(env_key, "")


def load_mcp_config(
    config_path: str | Path | None = None,
) -> dict[str, MCPServerConfig]:
    """
    从 mcp_servers.json 加载MCP服务器配置。

    Args:
        config_path: 配置文件路径，默认为 backend/mcp_servers.json

    Returns:
        服务器名称 → 配置的映射
    """
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent.parent / "mcp_servers.json"
    config_path = Path(config_path)

    if not config_path.exists():
        logger.info(f"MCP config not found at {config_path}, no servers configured")
        return {}

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load MCP config: {e}")
        return {}

    servers_raw = raw.get("servers", {})
    if not isinstance(servers_raw, dict):
        logger.warning("MCP config 'servers' must be a mapping")
        return {}

    configs: dict[str, MCPServerConfig] = {}
    for name, srv in servers_raw.items():
        if not isinstance(srv, dict) or "command" not in srv:
            logger.warning(f"Skipping invalid MCP server config: {name}")
            continue

        command = srv["command"]
        base_cmd = command.split("/")[-1].split("\\")[-1]
        if base_cmd not in _ALLOWED_COMMANDS:
            logger.warning(
                f"Skipping MCP server '{name}': "
                f"command '{base_cmd}' not in allowlist {sorted(_ALLOWED_COMMANDS)}"
            )
            continue

        args = srv.get("args", [])
        for arg in args:
            if isinstance(arg, str) and _SHELL_META_RE.search(arg):
                logger.warning(
                    f"Skipping MCP server '{name}': "
                    f"shell metacharacter in arg: {arg!r}"
                )
                break
        else:
            # Filter dangerous env vars
            raw_env = srv.get("env", {})
            if not isinstance(raw_env, dict):
                logger.warning(
                    f"Skipping MCP server '{name}': env must be a mapping"
                )
                raw_env = {}

            safe_env = {
                k: _resolve_env_value(v)
                for k, v in raw_env.items()
                if isinstance(k, str) and k.upper() not in _BLOCKED_ENV_VARS
            }
            if len(safe_env) < len(raw_env):
                blocked = set(raw_env) - set(safe_env)
                logger.warning(f"MCP server '{name}': blocked env vars {blocked}")

            configs[name] = MCPServerConfig(
                name=name,
                command=command,
                args=tuple(args),
                env=tuple(safe_env.items()),
                description=srv.get("description", ""),
            )
            continue

    logger.info(f"Loaded {len(configs)} MCP server configs")
    return configs
