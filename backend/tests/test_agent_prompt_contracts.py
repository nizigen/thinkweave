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
    assert "constraint_specification" in content
    assert "actionable_output_spec" in content


def test_researcher_prompt_mentions_source_scope_and_evidence_ledger():
    content = _read("researcher")
    assert "source policy" in content.lower()
    assert "keyword_plan" in content
    assert "evidence_ledger" in content
    assert "chapter_mapping" in content
    assert "source_url" in content
    assert "source_title" in content
    assert "published_at" in content


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
    assert "unapplied_recommendations" in content
    assert "repair_priority" in content
    assert "severity_summary" in content


def test_writer_support_prompts_exist_and_define_contracts():
    constraint_path = Path("prompts/writer/constraint_specification.md")
    actionable_path = Path("prompts/writer/actionable_output.md")
    if not constraint_path.exists():
        constraint_path = Path("backend/prompts/writer/constraint_specification.md")
    if not actionable_path.exists():
        actionable_path = Path("backend/prompts/writer/actionable_output.md")
    constraint = constraint_path.read_text(encoding="utf-8")
    actionable = actionable_path.read_text(encoding="utf-8")

    assert "可观察阈值" in constraint
    assert "ACTIONABLE_CHECKLIST" in actionable
    assert "DECISION_MATRIX" in actionable


def test_prompts_enforce_chinese_first_language_policy():
    writer = _read("writer")
    reviewer = _read("reviewer")
    consistency = _read("consistency")

    assert "正文默认使用简体中文" in writer
    assert "非必要不用英文整句" in writer
    assert "默认中文正文" in reviewer
    assert "language_policy_conflicts" in consistency
