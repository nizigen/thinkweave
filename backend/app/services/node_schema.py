"""Unified node output schema validation across roles."""

from __future__ import annotations

import json
from typing import Any

from app.services.writer_output import parse_writer_payload


def _parse_json_object(text: str) -> dict[str, Any] | None:
    body = (text or "").strip()
    if body.startswith("```"):
        lines = body.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        body = "\n".join(lines).strip()
    try:
        parsed = json.loads(body)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def has_valid_schema_for_role(role: str | None, content: str) -> bool:
    """Return True when node output satisfies role-level schema contract."""
    role_name = str(role or "").strip().lower()
    text = (content or "").strip()
    if not text:
        return False

    if role_name == "writer":
        return parse_writer_payload(text) is not None

    if role_name == "reviewer":
        parsed = _parse_json_object(text)
        if not parsed:
            return False
        keys = {str(k).lower() for k in parsed.keys()}
        required = {"score", "must_fix", "feedback", "pass"}
        return required.issubset(keys)

    if role_name == "consistency":
        parsed = _parse_json_object(text)
        if not parsed:
            return False
        keys = {str(k).lower() for k in parsed.keys()}
        required = {
            "pass",
            "style_conflicts",
            "claim_conflicts",
            "repair_targets",
            "repair_priority",
            "severity_summary",
        }
        return required.issubset(keys)

    if role_name == "researcher":
        parsed = _parse_json_object(text)
        if not parsed:
            return False
        keys = {str(k).lower() for k in parsed.keys()}
        required = {
            "topic_anchor",
            "source_scope",
            "keyword_plan",
            "evidence_ledger",
            "chapter_mapping",
            "uncertainty_flags",
        }
        return required.issubset(keys)

    # Outline and other roles currently allow plain markdown/text.
    return True

