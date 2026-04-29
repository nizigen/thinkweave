"""Utilities for writer node structured output contract."""

from __future__ import annotations

import json
import re
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


def _parse_json_objects_from_blob(text: str) -> list[dict[str, Any]]:
    body = _strip_code_fence(text)
    if not body:
        return []
    decoder = json.JSONDecoder()
    idx = 0
    out: list[dict[str, Any]] = []
    length = len(body)
    while idx < length:
        while idx < length and body[idx].isspace():
            idx += 1
        if idx >= length:
            break
        if body[idx] != "{":
            idx += 1
            continue
        try:
            obj, end = decoder.raw_decode(body, idx)
        except Exception:
            idx += 1
            continue
        if isinstance(obj, dict):
            out.append(obj)
        idx = max(end, idx + 1)
    return out


def _normalize_string_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        value = str(item or "").strip()
        if value:
            out.append(value)
    return out


def _split_markdown_paragraphs(markdown: str) -> list[str]:
    text = str(markdown or "").strip()
    if not text:
        return []
    parts = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    cleaned: list[str] = []
    for part in parts:
        if part.startswith("#"):
            continue
        cleaned.append(part)
    return cleaned


def _normalize_paragraphs(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    paragraphs: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
            citation_keys: list[str] = []
        elif isinstance(item, dict):
            text = str(item.get("text") or "").strip()
            citation_keys = _normalize_string_list(item.get("citation_keys"))
        else:
            continue
        if not text:
            continue
        paragraphs.append(
            {
                "text": text,
                "citation_keys": citation_keys,
            }
        )
    return paragraphs


def _payload_to_section(payload: dict[str, Any], *, default_heading: str = "") -> dict[str, Any] | None:
    heading = str(
        payload.get("heading")
        or payload.get("chapter_title")
        or default_heading
        or ""
    ).strip()
    paragraphs = _normalize_paragraphs(payload.get("paragraphs"))
    content = str(payload.get("content_markdown") or "").strip()
    if not paragraphs and content:
        paragraphs = [{"text": part, "citation_keys": []} for part in _split_markdown_paragraphs(content)]
    if not paragraphs:
        return None
    return {
        "heading": heading or "章节",
        "paragraphs": paragraphs,
    }


def parse_writer_payload(text: str) -> dict[str, Any] | None:
    """Parse and validate writer structured payload.

    Required fields:
    - chapter_title: str
    - content_markdown: str (non-empty)
    """
    parsed = _parse_json_object(text)
    if not parsed:
        return None

    heading = str(
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
    paragraphs = _normalize_paragraphs(parsed.get("paragraphs"))
    if not paragraphs and content_markdown:
        paragraphs = [
            {"text": part, "citation_keys": []}
            for part in _split_markdown_paragraphs(content_markdown)
        ]
    if not paragraphs and not content_markdown:
        return None
    if not content_markdown:
        content_markdown = "\n\n".join(item["text"] for item in paragraphs if item.get("text"))

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
            source_url = str(item.get("source_url") or "").strip()
            if not statement and not support:
                continue
            citation_ledger.append(
                {
                    "statement": statement,
                    "support": support,
                    "source_url": source_url,
                }
            )

    return {
        "chapter_title": heading,
        "heading": heading,
        "paragraphs": paragraphs,
        "content_markdown": content_markdown,
        "key_points": key_points,
        "evidence_trace": evidence_trace,
        "boundary_notes": boundary_notes,
        "citation_ledger": citation_ledger,
    }


def extract_writer_sections(text: str, *, default_heading: str = "") -> list[dict[str, Any]]:
    """Extract one or more writer sections from possibly mixed output text.

    Supports:
    - strict single JSON payload
    - multiple JSON objects concatenated in one blob
    - markdown/plain text fallback as a single section
    """
    sections: list[dict[str, Any]] = []

    payload = parse_writer_payload(text)
    if payload is not None:
        section = _payload_to_section(payload, default_heading=default_heading)
        if section is not None:
            return [section]

    json_blocks = _parse_json_objects_from_blob(text)
    for obj in json_blocks:
        parsed = parse_writer_payload(json.dumps(obj, ensure_ascii=False))
        if parsed is None:
            continue
        section = _payload_to_section(parsed, default_heading=default_heading)
        if section is not None:
            sections.append(section)
    if sections:
        return sections

    fallback_text = str(text or "").strip()
    if not fallback_text:
        return []
    return [
        {
            "heading": default_heading or "章节",
            "paragraphs": [{"text": fallback_text, "citation_keys": []}],
        }
    ]


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
    paragraphs = payload.get("paragraphs")
    if not content:
        issues.append("content_markdown_empty")
        return issues
    if not isinstance(paragraphs, list) or not paragraphs:
        issues.append("paragraphs_missing")
    else:
        for idx, item in enumerate(paragraphs):
            if not isinstance(item, dict):
                issues.append(f"paragraph_{idx}_invalid")
                continue
            if not str(item.get("text") or "").strip():
                issues.append(f"paragraph_{idx}_text_empty")
                continue
            raw_keys = item.get("citation_keys", [])
            if not isinstance(raw_keys, list):
                issues.append(f"paragraph_{idx}_citation_keys_invalid")
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
    # Konruns-style fallback: when output contains multiple JSON blobs
    # (or mixed JSON/plain text), extract paragraph text from each JSON object.
    json_blocks = _parse_json_objects_from_blob(text)
    if json_blocks:
        merged_parts: list[str] = []
        for obj in json_blocks:
            chapter_payload = parse_writer_payload(json.dumps(obj, ensure_ascii=False))
            if chapter_payload is None:
                continue
            chunk = str(chapter_payload.get("content_markdown") or "").strip()
            if chunk:
                merged_parts.append(chunk)
        if merged_parts:
            return "\n\n".join(merged_parts).strip()
    return (text or "").strip()


def make_fallback_writer_payload(*, chapter_title: str, content_markdown: str) -> dict[str, Any] | None:
    markdown = (content_markdown or "").strip()
    if not markdown:
        return None
    paragraphs = [
        {"text": part, "citation_keys": []}
        for part in _split_markdown_paragraphs(markdown)
    ]
    if not paragraphs:
        paragraphs = [{"text": markdown, "citation_keys": []}]
    return {
        "chapter_title": str(chapter_title or "").strip(),
        "heading": str(chapter_title or "").strip(),
        "paragraphs": paragraphs,
        "content_markdown": markdown,
        "key_points": [],
        "evidence_trace": [],
        "boundary_notes": [],
        "citation_ledger": [],
    }


def serialize_writer_payload(payload: dict[str, Any]) -> str:
    heading = str(
        payload.get("heading")
        or payload.get("chapter_title")
        or ""
    ).strip()
    paragraphs = _normalize_paragraphs(payload.get("paragraphs"))
    content = str(payload.get("content_markdown") or "").strip()
    if not paragraphs and content:
        paragraphs = [{"text": part, "citation_keys": []} for part in _split_markdown_paragraphs(content)]
    if not content and paragraphs:
        content = "\n\n".join(item["text"] for item in paragraphs if item.get("text"))
    normalized = {
        "heading": heading,
        "paragraphs": paragraphs,
        # Backward compatibility fields
        "chapter_title": heading,
        "content_markdown": content,
        "key_points": _normalize_string_list(payload.get("key_points")),
        "evidence_trace": payload.get("evidence_trace") if isinstance(payload.get("evidence_trace"), list) else [],
        "boundary_notes": _normalize_string_list(payload.get("boundary_notes")),
        "citation_ledger": payload.get("citation_ledger") if isinstance(payload.get("citation_ledger"), list) else [],
    }
    return json.dumps(normalized, ensure_ascii=False)
