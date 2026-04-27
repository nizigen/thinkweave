from __future__ import annotations

import json

from app.services.writer_output import (
    extract_writer_markdown,
    make_fallback_writer_payload,
    parse_writer_payload,
    validate_writer_payload,
)


def test_parse_writer_payload_accepts_valid_json():
    payload = {
        "chapter_title": "第1章",
        "content_markdown": "## 小节\n正文内容",
        "key_points": ["a", "b"],
        "evidence_trace": [{"claim": "c1", "evidence_ids": ["e1"]}],
        "boundary_notes": ["n1"],
    }
    parsed = parse_writer_payload(json.dumps(payload, ensure_ascii=False))
    assert parsed is not None
    assert parsed["chapter_title"] == "第1章"
    assert parsed["content_markdown"].startswith("## 小节")


def test_parse_writer_payload_rejects_missing_content():
    payload = {"chapter_title": "第1章", "key_points": ["a"]}
    assert parse_writer_payload(json.dumps(payload, ensure_ascii=False)) is None


def test_extract_writer_markdown_uses_structured_content():
    payload = {
        "chapter_title": "第2章",
        "content_markdown": "正文A\n\n正文B",
    }
    text = json.dumps(payload, ensure_ascii=False)
    assert extract_writer_markdown(text) == "正文A\n\n正文B"


def test_extract_writer_markdown_keeps_plain_text_for_backward_compatibility():
    plain = "# 章节\n旧版纯文本输出"
    assert extract_writer_markdown(plain) == plain


def test_make_fallback_writer_payload():
    payload = make_fallback_writer_payload(
        chapter_title="第3章",
        content_markdown="正文",
    )
    assert payload is not None
    assert payload["chapter_title"] == "第3章"
    assert payload["content_markdown"] == "正文"


def test_parse_writer_payload_keeps_citation_ledger():
    payload = {
        "chapter_title": "第4章",
        "content_markdown": "正文段落A\n\n正文段落B",
        "citation_ledger": [
            {"statement": "s1", "support": "E1", "source_url": "https://example.com/e1"},
            {"statement": "s2", "support": "uncertain"},
        ],
    }
    parsed = parse_writer_payload(json.dumps(payload, ensure_ascii=False))
    assert parsed is not None
    assert parsed["citation_ledger"][0]["support"] == "E1"
    assert parsed["citation_ledger"][0]["source_url"] == "https://example.com/e1"


def test_validate_writer_payload_flags_template_style():
    payload = {
        "chapter_title": "第5章",
        "content_markdown": (
            "首先，我们可以看到当前讨论的重点是流程优化。\n\n"
            "其次，我们可以看到当前讨论的重点是数据治理。\n\n"
            "最后，我们可以看到当前讨论的重点是风险控制。"
        ),
        "key_points": [],
        "evidence_trace": [],
        "boundary_notes": [],
        "citation_ledger": [],
    }
    issues = validate_writer_payload(payload)
    assert any(item.startswith("template:") for item in issues)
