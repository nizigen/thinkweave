"""Prompt contract tests for Stage 4.3 prompt hardening."""

from app.utils.prompt_loader import PromptLoader


def _assert_contains_all(content: str, required: list[str]) -> None:
    for needle in required:
        assert needle in content


def test_consistency_check_claims_prompt_contract():
    loader = PromptLoader()
    content = loader.load(
        "consistency",
        "check_claims",
        chapter_title="Sample Chapter",
        chapter_content="Sample content",
        chapter_claims="[]",
    )

    _assert_contains_all(
        content,
        [
            "verified|weak|unverifiable",
            '"claims": [',
            '"status": "verified|weak|unverifiable"',
        ],
    )


def test_reviewer_prompt_contract():
    loader = PromptLoader()
    content = loader.load(
        "reviewer",
        "review_chapter",
        chapter_index="1",
        chapter_title="Chapter",
        chapter_content="Body",
        chapter_description="Scope",
        overlap_findings="none",
        topic_claims="",
        assigned_evidence="",
    )
    _assert_contains_all(
        content,
        ['"must_fix": [', '"strongest_counterargument":', "pass=true only when score >= 70"],
    )


def test_revise_prompt_contract():
    loader = PromptLoader()
    content = loader.load(
        "writer",
        "revise_chapter",
        chapter_index="1",
        chapter_title="Chapter",
        original_content="Body",
        review_feedback="Fix issue",
        accuracy_score="80",
        coherence_score="81",
        style_score="79",
    )
    _assert_contains_all(
        content,
        ['### Revision Closure Table', '"issue":', '"action":', '"evidence":', '"status": "fixed|partial|not_fixed"'],
    )
