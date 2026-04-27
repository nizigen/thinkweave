from __future__ import annotations

import uuid

from app.services.evidence_pool import (
    classify_source_url,
    evidence_pool_markdown,
    normalize_evidence_ledger,
)


def test_classify_source_url_for_oa_and_patent():
    assert classify_source_url("https://arxiv.org/abs/1234.5678") == "oa"
    assert classify_source_url("https://patents.google.com/patent/US1234567A/en") == "patent"
    assert classify_source_url("https://www.worldbank.org/en/publication/example") == "industry_report"
    assert classify_source_url("https://www.gutenberg.org/ebooks/1342") == "fiction_reference"
    assert classify_source_url("https://example.com/post") == "other"


def test_normalize_evidence_ledger_enriches_source_kind():
    raw = [
        {
            "evidence_id": "E1",
            "claim_target": "claim",
            "source_url": "https://openalex.org/W123",
            "source_title": "title",
            "published_at": "2024-01-01",
            "required_source_type": "paper",
            "priority": "high",
        },
        {"evidence_id": ""},
    ]
    items = normalize_evidence_ledger(raw)
    assert len(items) == 1
    assert items[0]["source_kind"] == "oa"


def test_evidence_pool_markdown_contains_seed_sections_and_table():
    md = evidence_pool_markdown(
        task_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        title="测试任务",
        evidence_items=[
            {
                "evidence_id": "E2",
                "claim_target": "测试论断",
                "source_kind": "patent",
                "priority": "medium",
                "required_source_type": "official_report",
                "published_at": "2023-10-01",
                "source_title": "Patent Record",
                "source_url": "https://patentscope.wipo.int/search",
            }
        ],
        source_policy={"policy_name": "report_evidence_first"},
        research_keywords=["证据池", "专利"],
        mode="report",
    )
    assert "## Source Seeds" in md
    assert "### patent_urls" in md
    assert "### oa_urls" in md
    assert "### industry_report_urls" in md
    assert "| evidence_id | source_kind |" in md
    assert "E2" in md
