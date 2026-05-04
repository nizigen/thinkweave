from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "longform_eval_runner.py"


def _run_eval(*, task_detail_path: Path, output_path: Path, target_words: int = 30000) -> dict:
    env = os.environ.copy()
    env["TASK_DETAIL_JSON"] = str(task_detail_path)
    env["LONGFORM_EVAL_OUTPUT"] = str(output_path)
    env["TARGET_WORDS"] = str(target_words)
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert output_path.exists()
    return json.loads(output_path.read_text(encoding="utf-8"))


def test_longform_eval_runner_outputs_skipped_when_input_missing(tmp_path: Path):
    missing = tmp_path / "missing.json"
    output = tmp_path / "eval.json"
    payload = _run_eval(task_detail_path=missing, output_path=output)

    assert payload["status"] == "skipped"
    assert payload["metrics"]["length_compliance"] == 0
    assert payload["metrics"]["citation_coverage"] == 0


def test_longform_eval_runner_outputs_machine_readable_metrics(tmp_path: Path):
    detail = {
        "id": "task-1",
        "title": "30k longform",
        "status": "completed",
        "mode": "report",
        "depth": "deep",
        "word_count": 30000,
        "citation_summary": {"total": 10, "bound_to_evidence": 8},
        "evidence_summary": {"total": 20, "unbound_claims": 0},
        "checkpoint_data": {
            "consistency_repair_budget": {
                "total_points": 14,
                "spent_points": 6,
                "remaining_points": 8,
            }
        },
        "node_status_summary": {},
    }
    input_path = tmp_path / "task_detail.json"
    input_path.write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "eval.json"

    payload = _run_eval(task_detail_path=input_path, output_path=output)

    assert payload["status"] == "ok"
    assert payload["metrics"]["length_compliance"] == 1.0
    assert payload["metrics"]["citation_coverage"] == 0.8
    assert payload["metrics"]["instruction_adherence"] >= 0.66
    assert payload["metrics"]["consistency_severity_budget"]["total_points"] == 14
    assert payload["pass_fail"]["overall"] is True


def test_longform_eval_runner_fails_length_gate_when_short(tmp_path: Path):
    detail = {
        "id": "task-2",
        "title": "short report",
        "status": "completed",
        "mode": "report",
        "depth": "deep",
        "word_count": 12000,
        "citation_summary": {"total": 10, "bound_to_evidence": 8},
        "evidence_summary": {"total": 20, "unbound_claims": 0},
        "checkpoint_data": {},
        "node_status_summary": {},
    }
    input_path = tmp_path / "task_detail.json"
    input_path.write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "eval.json"

    payload = _run_eval(task_detail_path=input_path, output_path=output, target_words=30000)

    assert payload["metrics"]["length_compliance"] < 1.0
    assert payload["pass_fail"]["length_gate"] is False
    assert payload["pass_fail"]["overall"] is False


def test_longform_eval_runner_fails_diagnosis_evidence_gates_when_claims_unbound(tmp_path: Path):
    detail = {
        "id": "task-3",
        "title": "evidence weak report",
        "status": "completed",
        "mode": "report",
        "depth": "deep",
        "word_count": 30000,
        "citation_summary": {"total": 10, "bound_to_evidence": 2},
        "evidence_summary": {"total": 20, "unbound_claims": 3},
        "checkpoint_data": {},
        "node_status_summary": {},
    }
    input_path = tmp_path / "task_detail.json"
    input_path.write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "eval.json"

    payload = _run_eval(task_detail_path=input_path, output_path=output, target_words=30000)

    assert payload["metrics"]["length_compliance"] == 1.0
    assert payload["metrics"]["citation_coverage"] == 0.2
    assert payload["metrics"]["instruction_adherence"] < 0.66
    assert payload["pass_fail"]["adherence_gate"] is False
    assert payload["pass_fail"]["citation_gate"] is False
    assert payload["pass_fail"]["overall"] is False
