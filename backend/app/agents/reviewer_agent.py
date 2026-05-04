"""Dedicated reviewer agent for chapter quality checks."""

from __future__ import annotations

import json
from typing import Any

from app.agents.worker import WorkerAgent


class ReviewerAgent(WorkerAgent):
    """Specialized L2 agent for chapter review."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs["role"] = "reviewer"
        kwargs.setdefault("layer", 2)
        super().__init__(**kwargs)

    async def handle_task(self, ctx: dict[str, Any]) -> str:
        incoming_role = str(ctx.get("agent_role") or "reviewer").strip().lower()
        if incoming_role != "reviewer":
            return await super().handle_task(ctx)
        payload = dict(ctx.get("payload", {}))
        normalized_payload = {
            "depth": payload.get("depth", ""),
            "target_words": payload.get("target_words", ""),
            "chapter_index": payload.get("chapter_index", ""),
            "chapter_title": payload.get("chapter_title", ""),
            "chapter_content": payload.get("chapter_content", ""),
            "chapter_description": payload.get("chapter_description", ""),
            "overlap_findings": payload.get("overlap_findings", "none"),
            "topic_claims": payload.get("topic_claims", {}),
            "assigned_evidence": payload.get("assigned_evidence", []),
            "source_policy": payload.get("source_policy", ""),
            "research_protocol": payload.get("research_protocol", ""),
            "research_keywords": payload.get("research_keywords", ""),
            "evidence_pool_summary": payload.get("evidence_pool_summary", ""),
            "evidence_pool_markdown": payload.get("evidence_pool_markdown", ""),
        }

        result = await super().handle_task(
            {
                **ctx,
                "agent_role": "reviewer",
                "payload": normalized_payload,
            }
        )
        return self._enforce_evidence_review_policy(result)

    @staticmethod
    def _enforce_evidence_review_policy(result: str) -> str:
        text = str(result or "").strip()
        if not text:
            return text
        try:
            parsed = json.loads(text)
        except Exception:
            return text
        if not isinstance(parsed, dict):
            return text

        def _int_value(name: str, default: int = 0) -> int:
            try:
                return int(parsed.get(name, default))
            except Exception:
                return default

        must_fix = parsed.get("must_fix")
        if not isinstance(must_fix, list):
            must_fix = []
        must_fix = [str(item).strip() for item in must_fix if str(item).strip()]

        evidence_suff = _int_value("evidence_sufficiency_score")
        specificity = _int_value("specificity_score")
        source_attr = _int_value("source_attribution_score")
        overall = _int_value("score")

        if evidence_suff <= 60:
            must_fix.append("补充核心主张的证据绑定，列出 claim -> evidence_id 映射。")
        if specificity <= 60:
            must_fix.append("将泛化结论替换为可核验陈述，补充量化细节和边界条件。")
        if source_attr <= 60:
            must_fix.append("补充来源归因：每条关键陈述应给出来源或 missing 标记。")

        unsupported_claims = parsed.get("unsupported_claims")
        if not isinstance(unsupported_claims, list):
            unsupported_claims = []
        missing_sources = parsed.get("missing_sources")
        if not isinstance(missing_sources, list):
            missing_sources = []

        pass_flag = bool(parsed.get("pass", False))
        if must_fix or evidence_suff <= 60 or specificity <= 60 or source_attr <= 60:
            pass_flag = False

        repaired_score = min(
            overall if overall > 0 else 100,
            int(round((evidence_suff * 0.4) + (specificity * 0.3) + (source_attr * 0.3))),
        )
        parsed["score"] = max(0, min(100, repaired_score))
        parsed["must_fix"] = list(dict.fromkeys(must_fix))
        parsed["pass"] = pass_flag and parsed["score"] >= 72 and not parsed["must_fix"]
        parsed["unsupported_claims"] = unsupported_claims
        parsed["missing_sources"] = missing_sources
        if "specificity_score" not in parsed:
            parsed["specificity_score"] = specificity
        if "source_attribution_score" not in parsed:
            parsed["source_attribution_score"] = source_attr
        return json.dumps(parsed, ensure_ascii=False)
