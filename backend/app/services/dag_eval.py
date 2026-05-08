"""Evaluation metrics for DAG quality comparisons."""

from __future__ import annotations

from typing import Any


def _safe_div(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return num / den


def _f1_from_sets(
    predicted: set[str],
    actual: set[str],
) -> dict[str, float | int]:
    tp = len(predicted & actual)
    fp = len(predicted - actual)
    fn = len(actual - predicted)
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
    }


def _extract_node_ids(dag: dict[str, Any]) -> set[str]:
    nodes = dag.get("nodes", [])
    if not isinstance(nodes, list):
        return set()
    out: set[str] = set()
    for item in nodes:
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("id", "") or "").strip()
        if node_id:
            out.add(node_id)
    return out


def _extract_edges(dag: dict[str, Any]) -> set[tuple[str, str]]:
    nodes = dag.get("nodes", [])
    if not isinstance(nodes, list):
        return set()
    out: set[tuple[str, str]] = set()
    for item in nodes:
        if not isinstance(item, dict):
            continue
        child = str(item.get("id", "") or "").strip()
        if not child:
            continue
        deps = item.get("depends_on", [])
        if not isinstance(deps, list):
            continue
        for dep in deps:
            parent = str(dep or "").strip()
            if parent:
                out.add((parent, child))
    return out


def _extract_tools(snapshot: dict[str, Any]) -> set[str]:
    raw = snapshot.get("tools", [])
    if not isinstance(raw, list):
        return set()
    out: set[str] = set()
    for item in raw:
        token = str(item or "").strip().lower()
        if token:
            out.add(token)
    return out


def structural_similarity_index(
    predicted_dag: dict[str, Any],
    actual_dag: dict[str, Any],
) -> float:
    pred_edges = _extract_edges(predicted_dag)
    actual_edges = _extract_edges(actual_dag)
    union = pred_edges | actual_edges
    if not union:
        pred_nodes = _extract_node_ids(predicted_dag)
        actual_nodes = _extract_node_ids(actual_dag)
        return 1.0 if pred_nodes == actual_nodes else 0.0
    score = _safe_div(len(pred_edges & actual_edges), len(union))
    return round(score, 6)


def evaluate_dag_metrics(
    *,
    predicted_dag: dict[str, Any],
    actual_dag: dict[str, Any],
    predicted_tools: list[str] | None = None,
    actual_tools: list[str] | None = None,
) -> dict[str, Any]:
    predicted_nodes = _extract_node_ids(predicted_dag)
    actual_nodes = _extract_node_ids(actual_dag)
    node_f1 = _f1_from_sets(predicted_nodes, actual_nodes)

    predicted_tool_set = _extract_tools({"tools": predicted_tools or []})
    actual_tool_set = _extract_tools({"tools": actual_tools or []})
    tool_f1 = _f1_from_sets(predicted_tool_set, actual_tool_set)

    ssi = structural_similarity_index(predicted_dag, actual_dag)

    return {
        "ssi": ssi,
        "node_f1": node_f1,
        "tool_f1": tool_f1,
        "summary": {
            "predicted_node_count": len(predicted_nodes),
            "actual_node_count": len(actual_nodes),
            "predicted_tool_count": len(predicted_tool_set),
            "actual_tool_count": len(actual_tool_set),
        },
    }

