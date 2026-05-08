from __future__ import annotations

from app.services.mcts_engine import run_mcts_shadow
from app.services.strategy_catalog import build_strategy_candidates


def test_mcts_shadow_selects_from_five_candidates():
    candidates = build_strategy_candidates()
    result = run_mcts_shadow(
        candidates=candidates,
        mode="report",
        depth="deep",
        target_words=30000,
        ucb_c=1.4,
        iterations=32,
        seed_text="phase7-shadow",
    )
    assert len(result["candidates"]) == 5
    selected = result["selected_strategy"]
    assert selected in {candidate.strategy_id for candidate in candidates}
    assert result["iterations"] == 32


def test_mcts_shadow_is_deterministic_for_same_seed():
    candidates = build_strategy_candidates()
    left = run_mcts_shadow(
        candidates=candidates,
        mode="report",
        depth="standard",
        target_words=12000,
        ucb_c=1.4,
        iterations=32,
        seed_text="same-seed",
    )
    right = run_mcts_shadow(
        candidates=candidates,
        mode="report",
        depth="standard",
        target_words=12000,
        ucb_c=1.4,
        iterations=32,
        seed_text="same-seed",
    )
    assert left["selected_strategy"] == right["selected_strategy"]
    assert left["candidates"] == right["candidates"]

