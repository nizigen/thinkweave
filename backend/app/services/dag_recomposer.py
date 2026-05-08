"""Runtime DAG recomposition planning utilities."""

from __future__ import annotations

from typing import Any


def _normalize_targets(raw_targets: list[int]) -> list[int]:
    out: list[int] = []
    for raw in raw_targets:
        try:
            value = int(raw)
        except Exception:
            continue
        if value <= 0:
            continue
        if value in out:
            continue
        out.append(value)
    return out


def _count_existing_repair_waves(existing_titles: list[str]) -> int:
    return sum(
        1
        for title in existing_titles
        if "一致性定向修复（轮次" in str(title or "")
    )


def build_consistency_recompose_plan(
    *,
    existing_titles: list[str],
    repair_targets: list[int],
    depth: str,
    target_words: int,
    max_waves: int,
    quick_target_words_max: int,
) -> dict[str, Any]:
    wave_count = _count_existing_repair_waves(existing_titles)
    if wave_count >= max_waves:
        return {
            "should_inject": False,
            "reason": "wave_limit_exceeded",
            "wave_count": wave_count,
            "max_waves": max_waves,
            "insertions": [],
            "reconnects": [],
        }

    normalized_targets = _normalize_targets(repair_targets)
    if not normalized_targets:
        return {
            "should_inject": False,
            "reason": "no_valid_targets",
            "wave_count": wave_count,
            "max_waves": max_waves,
            "insertions": [],
            "reconnects": [],
        }

    wave_no = wave_count + 1
    mode = str(depth or "").strip().lower()
    quick_compact = mode == "quick" and 0 < int(target_words or 0) <= quick_target_words_max
    selected_targets = normalized_targets[:1] if quick_compact else normalized_targets[:4]

    insertions: list[dict[str, Any]] = []
    writer_keys: list[str] = []
    reviewer_keys: list[str] = []
    for chapter_index in selected_targets:
        writer_key = f"repair_writer_{wave_no}_{chapter_index}"
        writer_keys.append(writer_key)
        insertions.append(
            {
                "logical_id": writer_key,
                "title": f"第{chapter_index}章：一致性定向修复（轮次{wave_no}）",
                "agent_role": "writer",
                "status": "ready",
                "depends_on": [],
            }
        )
        if quick_compact:
            continue
        reviewer_key = f"repair_reviewer_{wave_no}_{chapter_index}"
        reviewer_keys.append(reviewer_key)
        insertions.append(
            {
                "logical_id": reviewer_key,
                "title": f"第{chapter_index}章：一致性修复审查（轮次{wave_no}）",
                "agent_role": "reviewer",
                "status": "pending",
                "depends_on": [writer_key],
            }
        )

    consistency_depends_on = writer_keys if quick_compact else reviewer_keys
    if not consistency_depends_on:
        return {
            "should_inject": False,
            "reason": "empty_consistency_dependencies",
            "wave_count": wave_count,
            "max_waves": max_waves,
            "insertions": [],
            "reconnects": [],
        }

    consistency_key = f"repair_consistency_{wave_no}"
    insertions.append(
        {
            "logical_id": consistency_key,
            "title": f"{'一致性快速复核' if quick_compact else '一致性复核'}（轮次{wave_no}）",
            "agent_role": "consistency",
            "status": "pending",
            "depends_on": consistency_depends_on,
        }
    )

    reconnects = [
        {
            "logical_id": consistency_key,
            "new_depends_on": consistency_depends_on,
            "mode": "replace",
        }
    ]

    return {
        "should_inject": True,
        "reason": "ok",
        "wave_count": wave_count,
        "wave_no": wave_no,
        "mode": "quick_compact" if quick_compact else "review_chain",
        "selected_targets": selected_targets,
        "insertions": insertions,
        "reconnects": reconnects,
    }

