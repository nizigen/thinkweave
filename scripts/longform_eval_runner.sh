#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INPUT_JSON="${TASK_DETAIL_JSON:-/tmp/pw_task_detail.json}"
OUTPUT_JSON="${LONGFORM_EVAL_OUTPUT:-/tmp/longform_eval.json}"
TARGET_WORDS="${TARGET_WORDS:-30000}"

if [[ ! -s "$INPUT_JSON" ]]; then
  jq -nc \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{
      status: "skipped",
      reason: "task detail json not found",
      evaluated_at: $ts,
      metrics: {
        length_compliance: 0,
        instruction_adherence: 0,
        citation_coverage: 0,
        duplicate_rate: null,
        consistency_severity_budget: null
      }
    }' >"$OUTPUT_JSON"
  cat "$OUTPUT_JSON"
  exit 0
fi

python3 - "$INPUT_JSON" "$OUTPUT_JSON" "$TARGET_WORDS" <<'PY'
import json
import sys
from datetime import datetime, timezone

input_path, output_path, target_raw = sys.argv[1:4]
try:
    target_words = int(target_raw)
except Exception:
    target_words = 30000

def safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default

with open(input_path, "r", encoding="utf-8") as f:
    detail = json.load(f)

word_count = safe_int(detail.get("word_count"), 0)
length_ratio = 0.0 if target_words <= 0 else (word_count / target_words)
length_compliance = round(min(1.0, max(0.0, length_ratio)), 4)

citation = detail.get("citation_summary") or {}
citation_total = safe_int(citation.get("total"), 0)
citation_bound = safe_int(citation.get("bound_to_evidence"), 0)
citation_coverage = round((citation_bound / citation_total), 4) if citation_total > 0 else 0.0

evidence = detail.get("evidence_summary") or {}
unbound_claims = safe_int(evidence.get("unbound_claims"), 0)

checkpoint = (detail.get("checkpoint_data") or {})
consistency_budget = checkpoint.get("consistency_repair_budget") or {}
remaining_points = safe_int(consistency_budget.get("remaining_points"), 0)
total_points = safe_int(consistency_budget.get("total_points"), 0)
spent_points = safe_int(consistency_budget.get("spent_points"), 0)

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
    dup = node_summary.get("duplicate_rate")
    try:
        if dup is not None:
            duplicate_rate = float(dup)
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

result = {
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

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(json.dumps(result, ensure_ascii=False, indent=2))
PY
