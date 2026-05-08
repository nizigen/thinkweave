from __future__ import annotations

from app.services.dag_recomposer import build_consistency_recompose_plan


def test_recompose_plan_quick_compact_injects_single_writer_path():
    plan = build_consistency_recompose_plan(
        existing_titles=[],
        repair_targets=[1, 2, 3],
        depth="quick",
        target_words=1200,
        max_waves=2,
        quick_target_words_max=2000,
    )
    assert plan["should_inject"] is True
    assert plan["mode"] == "quick_compact"
    assert plan["selected_targets"] == [1]
    roles = [item["agent_role"] for item in plan["insertions"]]
    assert roles.count("writer") == 1
    assert roles.count("reviewer") == 0
    assert roles.count("consistency") == 1


def test_recompose_plan_standard_builds_reviewer_chain():
    plan = build_consistency_recompose_plan(
        existing_titles=[],
        repair_targets=[1, 2, 3],
        depth="standard",
        target_words=4000,
        max_waves=2,
        quick_target_words_max=2000,
    )
    assert plan["should_inject"] is True
    assert plan["mode"] == "review_chain"
    roles = [item["agent_role"] for item in plan["insertions"]]
    assert roles.count("writer") == 3
    assert roles.count("reviewer") == 3
    assert roles.count("consistency") == 1
    reconnect = plan["reconnects"][0]
    assert reconnect["mode"] == "replace"
    assert len(reconnect["new_depends_on"]) == 3


def test_recompose_plan_stops_when_wave_limit_reached():
    plan = build_consistency_recompose_plan(
        existing_titles=[
            "第1章：一致性定向修复（轮次1）",
            "第2章：一致性定向修复（轮次2）",
        ],
        repair_targets=[1, 2],
        depth="standard",
        target_words=4000,
        max_waves=2,
        quick_target_words_max=2000,
    )
    assert plan["should_inject"] is False
    assert plan["reason"] == "wave_limit_exceeded"
    assert plan["insertions"] == []

