from __future__ import annotations

from pathlib import Path


PROMPTS = {
    "outline": Path("prompts/outline/generate.md"),
    "researcher": Path("prompts/researcher/research.md"),
    "writer": Path("prompts/writer/write_chapter.md"),
    "reviewer": Path("prompts/reviewer/review_chapter.md"),
    "consistency": Path("prompts/consistency/check.md"),
}


def _read(name: str) -> str:
    return PROMPTS[name].read_text(encoding="utf-8")


def test_outline_prompt_mentions_topic_claims_and_boundaries():
    content = _read("outline")
    assert "topic_claims" in content
    assert "boundary" in content.lower()


def test_writer_prompt_mentions_memory_topic_claims_and_evidence():
    content = _read("writer")
    assert "memory_context" in content.lower()
    assert "topic claims" in content.lower() or "topic_claims" in content
    assert "evidence" in content.lower()
    assert "source_policy" in content
    assert "research_protocol" in content
    assert "mechanical connector" in content.lower() or "首先/其次/最后" in content


def test_researcher_prompt_mentions_source_scope_and_evidence_ledger():
    content = _read("researcher")
    assert "source policy" in content.lower()
    assert "keyword_plan" in content
    assert "evidence_ledger" in content
    assert "chapter_mapping" in content


def test_reviewer_prompt_mentions_evidence_boundary_and_overlap_dimensions():
    content = _read("reviewer")
    assert "overlap_findings" in content
    assert "evidence" in content.lower()
    assert "boundary" in content.lower()
    assert "source_policy" in content
    assert "source_policy_compliance" in content


def test_consistency_prompt_mentions_structured_issue_families():
    content = _read("consistency")
    assert "style_conflicts" in content
    assert "duplicate_coverage" in content
    assert "transition_gaps" in content
    assert "term_inconsistency" in content
    assert "source_policy_violations" in content
