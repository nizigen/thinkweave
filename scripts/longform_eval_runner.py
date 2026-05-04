#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _build_skipped_payload() -> dict[str, Any]:
    return {
        "status": "skipped",
        "reason": "task detail json not found",
        "evaluated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "metrics": {
            "length_compliance": 0,
            "instruction_adherence": 0,
            "citation_coverage": 0,
            "duplicate_rate": None,
            "consistency_severity_budget": None,
        },
    }


def _build_eval_payload(detail: dict[str, Any], target_words: int) -> dict[str, Any]:
    word_count = _safe_int(detail.get("word_count"), 0)
    length_ratio = 0.0 if target_words <= 0 else (word_count / target_words)
    length_compliance = round(min(1.0, max(0.0, length_ratio)), 4)

    citation = detail.get("citation_summary") or {}
    citation_total = _safe_int(citation.get("total"), 0)
    citation_bound = _safe_int(citation.get("bound_to_evidence"), 0)
    citation_coverage = round((citation_bound / citation_total), 4) if citation_total > 0 else 0.0

    evidence = detail.get("evidence_summary") or {}
    unbound_claims = _safe_int(evidence.get("unbound_claims"), 0)

    checkpoint = detail.get("checkpoint_data") or {}
    consistency_budget = checkpoint.get("consistency_repair_budget") or {}
    total_points = _safe_int(consistency_budget.get("total_points"), 0)
    spent_points = _safe_int(consistency_budget.get("spent_points"), 0)
    remaining_points = _safe_int(consistency_budget.get("remaining_points"), 0)

    instruction_hits = 0
    instruction_total = 3
    if detail.get("mode") == "report":
        instruction_hits += 1
    if unbound_claims <= 0:
        instruction_hits += 1
    if citation_coverage >= 0.6:
        instruction_hits += 1
    instruction_adherence = round(instruction_hits / instruction_total, 4)

    duplicate_rate = None
    node_summary = detail.get("node_status_summary") or {}
    if isinstance(node_summary, dict):
        duplicate_value = node_summary.get("duplicate_rate")
        try:
            if duplicate_value is not None:
                duplicate_rate = float(duplicate_value)
        except Exception:
            duplicate_rate = None

    consistency_severity_budget = None
    if total_points > 0:
        consistency_severity_budget = {
            "total_points": total_points,
            "spent_points": spent_points,
            "remaining_points": remaining_points,
            "spent_ratio": round(spent_points / total_points, 4),
        }

    return {
        "status": "ok",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "task": {
            "id": detail.get("id"),
            "title": detail.get("title"),
            "mode": detail.get("mode"),
            "depth": detail.get("depth"),
            "target_words": target_words,
            "word_count": word_count,
            "task_status": detail.get("status"),
        },
        "metrics": {
            "length_compliance": length_compliance,
            "instruction_adherence": instruction_adherence,
            "citation_coverage": citation_coverage,
            "duplicate_rate": duplicate_rate,
            "consistency_severity_budget": consistency_severity_budget,
        },
        "pass_fail": {
            "length_gate": length_compliance >= 1.0,
            "adherence_gate": instruction_adherence >= 0.66,
            "citation_gate": citation_coverage >= 0.6,
            "overall": (
                length_compliance >= 1.0
                and instruction_adherence >= 0.66
                and citation_coverage >= 0.6
            ),
        },
    }


def main() -> int:
    input_json = Path(os.getenv("TASK_DETAIL_JSON", "/tmp/pw_task_detail.json"))
    output_json = Path(os.getenv("LONGFORM_EVAL_OUTPUT", "/tmp/longform_eval.json"))
    target_words = _safe_int(os.getenv("TARGET_WORDS", "30000"), 30000)

    if not input_json.exists() or input_json.stat().st_size <= 0:
        payload = _build_skipped_payload()
        output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    detail = json.loads(input_json.read_text(encoding="utf-8"))
    payload = _build_eval_payload(detail=detail, target_words=target_words)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
