"""Unified node output schema validation across roles."""

from __future__ import annotations

import json
from typing import Any

from app.services.writer_output import (
    make_fallback_writer_payload,
    parse_writer_payload,
    serialize_writer_payload,
)


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


def _normalize_string_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        value = str(item or "").strip()
        if value:
            out.append(value)
    return out


def _normalize_int(raw: Any, default: int = 0) -> int:
    try:
        return int(raw)
    except Exception:
        return default


def _normalize_bool(raw: Any, default: bool = False) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        token = raw.strip().lower()
        if token in {"true", "1", "yes", "y"}:
            return True
        if token in {"false", "0", "no", "n"}:
            return False
    return default


def _clamp_score(value: int) -> int:
    return max(0, min(100, int(value)))


def _coerce_writer_output(content: str, *, node_title: str = "") -> str | None:
    parsed = parse_writer_payload(content)
    if parsed is not None:
        return serialize_writer_payload(parsed)

    payload = _parse_json_object(content) or {}
    chapter_title = str(
        payload.get("chapter_title")
        or payload.get("heading")
        or payload.get("title")
        or node_title
        or "章节"
    ).strip()

    content_markdown = ""
    for key in (
        "content_markdown",
        "chapter_markdown",
        "content",
        "text",
        "body",
        "draft",
    ):
        candidate = str(payload.get(key) or "").strip()
        if candidate:
            content_markdown = candidate
            break

    if not content_markdown:
        content_markdown = str(content or "").strip()
    if not content_markdown:
        content_markdown = (
            f"# {chapter_title}\n\n"
            "（自动结构化兜底：上游输出未满足 writer schema，已保留章节占位，"
            "后续轮次会继续补写。）"
        )

    fallback = make_fallback_writer_payload(
        chapter_title=chapter_title,
        content_markdown=content_markdown,
    )
    if fallback is None:
        return None
    return serialize_writer_payload(fallback)


def _coerce_reviewer_output(content: str) -> str:
    parsed = _parse_json_object(content) or {}
    must_fix = _normalize_string_list(parsed.get("must_fix"))
    if not must_fix:
        must_fix = ["补充结构化 reviewer 输出，明确关键修复项。"]
    payload = {
        "score": _clamp_score(_normalize_int(parsed.get("score"), 60)),
        "must_fix": must_fix,
        "feedback": str(
            parsed.get("feedback")
            or parsed.get("summary")
            or "结构化修复：原 reviewer 输出未满足 schema，已自动兜底。"
        ).strip(),
        "pass": _normalize_bool(parsed.get("pass"), False),
        "accuracy_score": _clamp_score(_normalize_int(parsed.get("accuracy_score"), 0)),
        "coherence_score": _clamp_score(_normalize_int(parsed.get("coherence_score"), 0)),
        "evidence_sufficiency_score": _clamp_score(
            _normalize_int(parsed.get("evidence_sufficiency_score"), 0)
        ),
        "boundary_compliance_score": _clamp_score(
            _normalize_int(parsed.get("boundary_compliance_score"), 0)
        ),
        "non_overlap_score": _clamp_score(_normalize_int(parsed.get("non_overlap_score"), 0)),
        "strongest_counterargument": str(parsed.get("strongest_counterargument") or "").strip(),
    }
    return json.dumps(payload, ensure_ascii=False)


def _coerce_consistency_output(content: str) -> str:
    parsed = _parse_json_object(content) or {}
    payload = {
        "pass": _normalize_bool(parsed.get("pass"), True),
        "style_conflicts": parsed.get("style_conflicts")
        if isinstance(parsed.get("style_conflicts"), list)
        else [],
        "claim_conflicts": parsed.get("claim_conflicts")
        if isinstance(parsed.get("claim_conflicts"), list)
        else [],
        "duplicate_coverage": parsed.get("duplicate_coverage")
        if isinstance(parsed.get("duplicate_coverage"), list)
        else [],
        "term_inconsistency": parsed.get("term_inconsistency")
        if isinstance(parsed.get("term_inconsistency"), list)
        else [],
        "transition_gaps": parsed.get("transition_gaps")
        if isinstance(parsed.get("transition_gaps"), list)
        else [],
        "language_policy_conflicts": parsed.get("language_policy_conflicts")
        if isinstance(parsed.get("language_policy_conflicts"), list)
        else [],
        "source_policy_violations": parsed.get("source_policy_violations")
        if isinstance(parsed.get("source_policy_violations"), list)
        else [],
        "severity_summary": parsed.get("severity_summary")
        if isinstance(parsed.get("severity_summary"), dict)
        else {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "repair_priority": parsed.get("repair_priority")
        if isinstance(parsed.get("repair_priority"), list)
        else [],
        "repair_targets": parsed.get("repair_targets")
        if isinstance(parsed.get("repair_targets"), list)
        else [],
    }
    return json.dumps(payload, ensure_ascii=False)


def _coerce_researcher_output(content: str, *, node_title: str = "") -> str:
    parsed = _parse_json_object(content) or {}
    payload = {
        "topic_anchor": str(parsed.get("topic_anchor") or node_title or "").strip(),
        "source_scope": parsed.get("source_scope")
        if isinstance(parsed.get("source_scope"), dict)
        else {"allowed": [], "disallowed": [], "time_window": ""},
        "keyword_plan": parsed.get("keyword_plan")
        if isinstance(parsed.get("keyword_plan"), list)
        else [{"bucket": "definition", "queries": []}],
        "evidence_ledger": parsed.get("evidence_ledger")
        if isinstance(parsed.get("evidence_ledger"), list)
        else [],
        "chapter_mapping": parsed.get("chapter_mapping")
        if isinstance(parsed.get("chapter_mapping"), list)
        else [],
        "uncertainty_flags": parsed.get("uncertainty_flags")
        if isinstance(parsed.get("uncertainty_flags"), list)
        else [],
    }
    return json.dumps(payload, ensure_ascii=False)


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
        required = {"score", "must_fix", "feedback", "pass"}
        if not required.issubset({str(k).lower() for k in parsed.keys()}):
            return False
        if not isinstance(parsed.get("must_fix"), list):
            return False
        if not isinstance(parsed.get("feedback"), str):
            return False
        if not isinstance(parsed.get("pass"), bool):
            return False
        return True

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
        if not required.issubset(keys):
            return False
        if not isinstance(parsed.get("pass"), bool):
            return False
        for k in (
            "style_conflicts",
            "claim_conflicts",
            "repair_priority",
            "repair_targets",
        ):
            if not isinstance(parsed.get(k), list):
                return False
        for k in (
            "duplicate_coverage",
            "term_inconsistency",
            "transition_gaps",
            "language_policy_conflicts",
            "source_policy_violations",
        ):
            if k in parsed and not isinstance(parsed.get(k), list):
                return False
        if not isinstance(parsed.get("severity_summary"), dict):
            return False
        return True

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
        if not required.issubset(keys):
            return False
        if not isinstance(parsed.get("topic_anchor"), str):
            return False
        if not isinstance(parsed.get("source_scope"), dict):
            return False
        if not isinstance(parsed.get("keyword_plan"), list):
            return False
        if not isinstance(parsed.get("evidence_ledger"), list):
            return False
        if not isinstance(parsed.get("chapter_mapping"), list):
            return False
        if not isinstance(parsed.get("uncertainty_flags"), list):
            return False
        return True

    # Outline and other roles currently allow plain markdown/text.
    return True


def coerce_output_to_role_schema(
    role: str | None,
    content: str,
    *,
    node_title: str = "",
) -> str | None:
    """Best-effort normalization into role schema.

    Returns normalized text when repair is possible, otherwise None.
    """
    role_name = str(role or "").strip().lower()
    text = str(content or "").strip()

    if not role_name:
        return text or None
    if has_valid_schema_for_role(role_name, text):
        return text

    if role_name == "writer":
        return _coerce_writer_output(text, node_title=node_title)
    if role_name == "reviewer":
        return _coerce_reviewer_output(text)
    if role_name == "consistency":
        return _coerce_consistency_output(text)
    if role_name == "researcher":
        return _coerce_researcher_output(text, node_title=node_title)

    return text or None
