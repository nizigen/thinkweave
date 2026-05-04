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
            "默认中文表述",
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
        source_policy="",
        research_protocol="",
        research_keywords="",
        evidence_pool_summary="",
        evidence_pool_markdown="",
    )
    _assert_contains_all(
        content,
        [
            '"must_fix": [',
            '"strongest_counterargument":',
            "score >= 72",
            '"specificity_score":',
            '"source_attribution_score":',
            '"unsupported_claims":',
            '"missing_sources":',
        ],
    )


def test_outline_prompt_contract_requires_premise_gate_fields():
    loader = PromptLoader()
    content = loader.load(
        "outline",
        "generate",
        title="topic",
        mode="report",
        depth="standard",
        target_words=10000,
        draft_text="",
        review_comments="",
        style_requirements="",
        source_policy="",
        research_keywords="",
        evidence_pool_summary="",
        evidence_pool_markdown="",
    )
    _assert_contains_all(
        content,
        ["core_thesis", "primary_chapters", "optional_chapters", "thesis_contribution"],
    )


def test_writer_prompt_contract_requires_claim_evidence_mapping():
    loader = PromptLoader()
    content = loader.load(
        "writer",
        "write_chapter",
        chapter_index="1",
        chapter_title="Chapter",
        stage_code="DRAFT",
        schema_version="v2",
        stage_contract="",
        full_outline="",
        chapter_description="",
        context_bridges="",
        memory_context="",
        topic_claims="",
        assigned_evidence="",
        source_policy="",
        research_protocol="",
        research_keywords="",
        evidence_pool_summary="",
        evidence_pool_markdown="",
        target_words="1200",
        task_target_words="10000",
        node_target_words="1200",
        is_assembly_editor="false",
        title_level_rule="<=2",
        evidence_rule="strict",
        constraint_specification="",
        actionable_output_spec="",
    )
    _assert_contains_all(
        content,
        [
            "claim_evidence_map",
            "missing_evidence_items",
            "@evidence[MISSING:",
            "constraint_specification",
            "actionable_output_spec",
        ],
    )


def test_consistency_prompt_contract_mentions_unapplied_recommendations():
    loader = PromptLoader()
    content = loader.load(
        "consistency",
        "check",
        target_words="10000",
        chapters_summary="",
        key_fragments="",
        full_text="",
        topic_claims="",
        chapter_metadata="",
        source_policy="",
        research_keywords="",
        evidence_pool_summary="",
        evidence_pool_markdown="",
    )
    _assert_contains_all(content, ["unapplied_recommendations", "后文提出建议但前文未执行"])


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
        ["## Revision Closure Table", '"issue":', '"action":', '"evidence":', '"status": "fixed|partial|not_fixed"'],
    )
