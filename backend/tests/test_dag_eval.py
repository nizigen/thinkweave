from __future__ import annotations

from app.services.dag_eval import evaluate_dag_metrics, structural_similarity_index


def test_structural_similarity_index_matches_edges():
    predicted = {
        "nodes": [
            {"id": "n1", "depends_on": []},
            {"id": "n2", "depends_on": ["n1"]},
            {"id": "n3", "depends_on": ["n2"]},
        ]
    }
    actual = {
        "nodes": [
            {"id": "n1", "depends_on": []},
            {"id": "n2", "depends_on": ["n1"]},
            {"id": "n3", "depends_on": ["n1"]},
        ]
    }
    assert structural_similarity_index(predicted, actual) == 0.333333


def test_evaluate_dag_metrics_reports_f1_and_summary():
    predicted = {
        "nodes": [
            {"id": "outline", "depends_on": []},
            {"id": "writer", "depends_on": ["outline"]},
            {"id": "reviewer", "depends_on": ["writer"]},
        ]
    }
    actual = {
        "nodes": [
            {"id": "outline", "depends_on": []},
            {"id": "writer", "depends_on": ["outline"]},
            {"id": "consistency", "depends_on": ["writer"]},
        ]
    }
    result = evaluate_dag_metrics(
        predicted_dag=predicted,
        actual_dag=actual,
        predicted_tools=["search", "summarize"],
        actual_tools=["search", "verify"],
    )
    assert result["node_f1"]["tp"] == 2
    assert result["node_f1"]["fp"] == 1
    assert result["node_f1"]["fn"] == 1
    assert result["tool_f1"]["tp"] == 1
    assert result["summary"]["predicted_node_count"] == 3
    assert result["summary"]["actual_node_count"] == 3


def test_evaluate_dag_metrics_handles_empty_payloads():
    result = evaluate_dag_metrics(
        predicted_dag={},
        actual_dag={},
        predicted_tools=None,
        actual_tools=None,
    )
    assert result["ssi"] == 1.0
    assert result["node_f1"]["f1"] == 0.0
    assert result["tool_f1"]["f1"] == 0.0

