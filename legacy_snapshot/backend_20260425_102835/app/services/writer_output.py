"""Utilities for writer node structured output contract."""

from __future__ import annotations

import json
from typing import Any

WRITER_CONTAMINATION_PHRASES = (
    "可以看到当前讨论的重点",
    "扩写轮次继续补充了执行细节",
    "模型是否可用",
)

TEMPLATE_CONNECTORS = (
    "首先",
    "其次",
    "最后",
    "综上所述",
    "总的来说",
    "总体而言",
    "在此基础上",
    "进一步来看",
    "可以看出",
)


def _strip_code_fence(text: str) -> str:
    body = (text or "").strip()
    if not body.startswith("```"):
        return body
    lines = body.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_json_object(text: str) -> dict[str, Any] | None:
    body = _strip_code_fence(text)
    if not body:
        return None
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


def parse_writer_payload(text: str) -> dict[str, Any] | None:
    """Parse and validate writer structured payload.

    Required fields:
    - chapter_title: str
    - content_markdown: str (non-empty)
    """
    parsed = _parse_json_object(text)
    if not parsed:
        return None

    chapter_title = str(
        parsed.get("chapter_title")
        or parsed.get("heading")
        or parsed.get("title")
        or ""
    ).strip()
    content_markdown = str(
        parsed.get("content_markdown")
        or parsed.get("chapter_markdown")
        or parsed.get("content")
        or ""
    ).strip()
    if not content_markdown:
        return None

    key_points = _normalize_string_list(parsed.get("key_points"))
    boundary_notes = _normalize_string_list(parsed.get("boundary_notes"))

    evidence_trace: list[dict[str, Any]] = []
    raw_trace = parsed.get("evidence_trace")
    if isinstance(raw_trace, list):
        for item in raw_trace:
            if not isinstance(item, dict):
                continue
            claim = str(item.get("claim") or "").strip()
            evidence_ids = _normalize_string_list(item.get("evidence_ids"))
            if not claim and not evidence_ids:
                continue
            evidence_trace.append({"claim": claim, "evidence_ids": evidence_ids})

    citation_ledger: list[dict[str, Any]] = []
    raw_ledger = parsed.get("citation_ledger")
    if isinstance(raw_ledger, list):
        for item in raw_ledger:
            if not isinstance(item, dict):
                continue
            statement = str(item.get("statement") or "").strip()
            support = str(item.get("support") or "").strip()
            if not statement and not support:
                continue
            citation_ledger.append({"statement": statement, "support": support})

    return {
        "chapter_title": chapter_title,
        "content_markdown": content_markdown,
        "key_points": key_points,
        "evidence_trace": evidence_trace,
        "boundary_notes": boundary_notes,
        "citation_ledger": citation_ledger,
    }


def _split_paragraphs(content: str) -> list[str]:
    return [part.strip() for part in content.split("\n\n") if part.strip()]


def _template_style_issues(content: str) -> list[str]:
    issues: list[str] = []
    paragraphs = _split_paragraphs(content)
    if not paragraphs:
        return issues

    starts = [p[:14] for p in paragraphs if p]
    if starts:
        top_start = max(set(starts), key=starts.count)
        if starts.count(top_start) >= max(3, len(starts) // 2 + 1):
            issues.append("template:repetitive_paragraph_opening")

    connector_hits = sum(content.count(connector) for connector in TEMPLATE_CONNECTORS)
    if connector_hits >= 6:
        issues.append("template:connector_overuse")

    if {"首先", "其次", "最后"}.issubset({c for c in TEMPLATE_CONNECTORS if c in content}):
        issues.append("template:listicle_progression")

    normalized = ["".join(ch for ch in p if not ch.isspace()) for p in paragraphs]
    if len(set(normalized)) <= max(1, len(normalized) // 2):
        issues.append("template:paragraph_duplication")

    return issues


def validate_writer_payload(payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    content = str(payload.get("content_markdown") or "").strip()
    if not content:
        issues.append("content_markdown_empty")
        return issues
    if len(content) < 40:
        issues.append("content_too_short")
    for phrase in WRITER_CONTAMINATION_PHRASES:
        if phrase in content:
            issues.append(f"contamination:{phrase}")
    issues.extend(_template_style_issues(content))
    return issues


def is_valid_writer_output_text(text: str) -> bool:
    payload = parse_writer_payload(text)
    if payload is None:
        return False
    return not validate_writer_payload(payload)


def extract_writer_markdown(text: str) -> str:
    """Return normalized chapter markdown from writer output."""
    payload = parse_writer_payload(text)
    if payload is not None:
        return str(payload.get("content_markdown") or "").strip()
    return (text or "").strip()


def make_fallback_writer_payload(*, chapter_title: str, content_markdown: str) -> dict[str, Any] | None:
    markdown = (content_markdown or "").strip()
    if not markdown:
        return None
    return {
        "chapter_title": str(chapter_title or "").strip(),
        "content_markdown": markdown,
        "key_points": [],
        "evidence_trace": [],
        "boundary_notes": [],
        "citation_ledger": [],
    }


def serialize_writer_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)
