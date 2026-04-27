"""Stage contracts inspired by KonrunsGPT report pipeline.

Provides explicit stage semantics and per-stage constraints so each DAG node
runs under a deterministic contract instead of free-form generation.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "thinkweave.v1"

# KonrunsGPT-style stage map, adapted to current DAG runtime with semantic stage codes.
STAGE_CONTRACTS: dict[str, dict[str, Any]] = {
    "SCOPING": {
        "name": "主题解析与检索计划",
        "goal": "明确主题边界、检索问题与证据需求",
        "must": ["scope_clarity", "question_set", "evidence_plan"],
    },
    "RESEARCH": {
        "name": "检索与去重",
        "goal": "收集并去重可引用证据",
        "must": ["source_policy", "dedup_keys", "evidence_pool"],
    },
    "OUTLINE": {
        "name": "提纲生成",
        "goal": "生成可执行章节结构",
        "must": ["6_to_8_primary_sections", "clear_boundaries", "no_deep_heading"],
    },
    "DRAFT": {
        "name": "分章节草稿",
        "goal": "按章节生成结构化正文与证据映射",
        "must": ["chapter_scope_lock", "evidence_trace", "json_output_only"],
    },
    "REVIEW": {
        "name": "审查与一致性前置",
        "goal": "审核章节质量并识别冲突/重叠",
        "must": ["pass_flag", "must_fix", "repair_targets"],
    },
    "ASSEMBLY": {
        "name": "终稿拼装与润色",
        "goal": "跨章节整合、扩写、收敛",
        "must": ["cross_chapter_consistency", "length_closure", "style_unification"],
    },
    "QA": {
        "name": "质量校验",
        "goal": "校验字数、结构、引用完整性",
        "must": ["target_words_gate", "schema_gate", "failure_transparency"],
    },
}


ROLE_STAGE_DEFAULT: dict[str, str] = {
    "outline": "OUTLINE",
    "researcher": "RESEARCH",
    "writer": "DRAFT",
    "reviewer": "REVIEW",
    "consistency": "ASSEMBLY",
}

LEGACY_STAGE_ALIAS: dict[str, str] = {
    "A": "SCOPING",
    "B": "RESEARCH",
    "C": "OUTLINE",
    "D": "DRAFT",
    "E": "REVIEW",
    "F": "ASSEMBLY",
    "G": "ASSEMBLY",
    "H": "QA",
}


def resolve_stage_code(*, role: str | None, title: str | None = None) -> str:
    role_name = str(role or "").strip().lower()
    text = str(title or "").lower()
    if role_name == "writer" and "assembly编辑收敛" in text:
        return "ASSEMBLY"
    if role_name == "writer" and "扩写" in text:
        return "ASSEMBLY"
    if role_name == "writer" and "篇幅补足" in text:
        return "ASSEMBLY"
    if role_name == "writer" and "收敛" in text:
        return "ASSEMBLY"
    return ROLE_STAGE_DEFAULT.get(role_name, "QA")


def get_stage_contract(stage_code: str) -> dict[str, Any]:
    raw = str(stage_code or "").strip().upper()
    code = LEGACY_STAGE_ALIAS.get(raw, raw)
    return STAGE_CONTRACTS.get(code, STAGE_CONTRACTS["QA"])
