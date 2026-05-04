"""Dedicated consistency agent for full-document checks."""

from __future__ import annotations

import json
import re
from typing import Any

from app.agents.worker import WorkerAgent


class ConsistencyAgent(WorkerAgent):
    """Specialized L2 agent for cross-chapter consistency checks."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs["role"] = "consistency"
        kwargs.setdefault("layer", 2)
        super().__init__(**kwargs)

    async def handle_task(self, ctx: dict[str, Any]) -> str:
        incoming_role = str(ctx.get("agent_role") or "consistency").strip().lower()
        if incoming_role != "consistency":
            return await super().handle_task(ctx)
        payload = dict(ctx.get("payload", {}))
        normalized_payload = {
            "depth": payload.get("depth", ""),
            "target_words": payload.get("target_words", ""),
            "chapters_summary": payload.get("chapters_summary", ""),
            "full_text": payload.get("full_text", payload.get("full_draft", "")),
            "topic_claims": payload.get("topic_claims", []),
            "chapter_metadata": payload.get("chapter_metadata", []),
            "source_policy": payload.get("source_policy", ""),
            "research_keywords": payload.get("research_keywords", ""),
            "evidence_pool_summary": payload.get("evidence_pool_summary", ""),
            "evidence_pool_markdown": payload.get("evidence_pool_markdown", ""),
        }
        result = await super().handle_task(
            {
                **ctx,
                "agent_role": "consistency",
                "payload": normalized_payload,
            }
        )
        return self._enforce_recommendation_application(
            result=result,
            full_text=str(normalized_payload.get("full_text") or ""),
        )

    @staticmethod
    def _enforce_recommendation_application(*, result: str, full_text: str) -> str:
        text = str(result or "").strip()
        if not text:
            return text
        try:
            parsed = json.loads(text)
        except Exception:
            return text
        if not isinstance(parsed, dict):
            return text

        unapplied = parsed.get("unapplied_recommendations")
        if not isinstance(unapplied, list):
            unapplied = []
        detected = ConsistencyAgent._detect_unapplied_recommendations(full_text)
        if detected:
            unapplied.extend(detected)
            parsed["pass"] = False
            existing_targets = parsed.get("repair_targets")
            targets = existing_targets if isinstance(existing_targets, list) else []
            chapter_indexes = [
                int(item.get("chapter_index"))
                for item in detected
                if isinstance(item, dict) and str(item.get("chapter_index") or "").isdigit()
            ]
            for chapter_idx in chapter_indexes:
                if chapter_idx not in targets:
                    targets.append(chapter_idx)
            parsed["repair_targets"] = targets

            summary = parsed.get("severity_summary")
            if not isinstance(summary, dict):
                summary = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            try:
                summary["high"] = int(summary.get("high", 0) or 0) + len(detected)
            except Exception:
                summary["high"] = len(detected)
            parsed["severity_summary"] = summary

        parsed["unapplied_recommendations"] = unapplied
        return json.dumps(parsed, ensure_ascii=False)

    @staticmethod
    def _detect_unapplied_recommendations(full_text: str) -> list[dict[str, Any]]:
        body = str(full_text or "").strip()
        if not body:
            return []
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        out: list[dict[str, Any]] = []
        current_chapter = 0
        recommendation_patterns = ("建议", "应当", "需要", "需", "should", "recommended")
        scoped_markers = ("后续工作", "future work", "out-of-scope", "out of scope", "后续阶段", "暂不实施")
        for idx, line in enumerate(lines):
            chapter_match = re.search(r"第\s*(\d+)\s*章", line)
            if chapter_match:
                try:
                    current_chapter = int(chapter_match.group(1))
                except Exception:
                    current_chapter = 0
                continue
            lowered = line.lower()
            if not any(pattern in line or pattern in lowered for pattern in recommendation_patterns):
                continue
            if any(marker in line or marker in lowered for marker in scoped_markers):
                continue
            if current_chapter <= 0:
                continue
            previous_text = "\n".join(lines[:idx]).lower()
            keyword_hits = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{4,}", line)
            keyword_hits = [kw.lower() for kw in keyword_hits if kw.lower() not in {"should", "recommended"}]
            if not keyword_hits:
                continue
            if any(keyword in previous_text for keyword in keyword_hits[:4]):
                continue
            out.append(
                {
                    "chapter_index": current_chapter,
                    "problem": "后文提出建议但前文未执行或未落地说明",
                    "recommendation": line[:160],
                    "severity": "high",
                }
            )
        return out
