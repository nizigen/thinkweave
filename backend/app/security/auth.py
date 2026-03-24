"""Authentication and authorization helpers shared by routers."""

from __future__ import annotations

from dataclasses import dataclass
import hmac

from fastapi import Depends, Header, HTTPException

from app.config import settings


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    token: str
    is_admin: bool


def _parse_token_user_map(raw: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in (raw or "").split(","):
        pair = item.strip()
        if not pair or ":" not in pair:
            continue
        token, user = pair.split(":", 1)
        token = token.strip()
        user = user.strip()
        if token and user:
            mapping[token] = user
    return mapping


def _parse_admin_users(raw: str) -> set[str]:
    return {u.strip() for u in (raw or "").split(",") if u.strip()}


def _resolve_user_id_for_token(token: str, token_map: dict[str, str]) -> str:
    for candidate, user_id in token_map.items():
        if hmac.compare_digest(candidate, token):
            return user_id
    return ""


def require_auth_context(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> AuthContext:
    value = (authorization or "").strip()
    if not value.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = value[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token_map = _parse_token_user_map(settings.task_auth_tokens)
    user_id = _resolve_user_id_for_token(token, token_map)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid bearer token")

    admin_users = _parse_admin_users(settings.admin_user_ids)
    return AuthContext(
        user_id=user_id,
        token=token,
        is_admin=user_id in admin_users,
    )


def require_user_id(ctx: AuthContext = Depends(require_auth_context)) -> str:
    return ctx.user_id


def require_admin_user_id(
    ctx: AuthContext = Depends(require_auth_context),
) -> str:
    if not ctx.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return ctx.user_id
