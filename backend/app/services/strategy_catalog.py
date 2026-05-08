"""Static strategy catalog for MCTS shadow selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StrategyCandidate:
    strategy_id: str
    name: str
    profile: dict[str, Any]


def build_strategy_candidates() -> list[StrategyCandidate]:
    return [
        StrategyCandidate(
            strategy_id="reliability_first",
            name="Reliability First",
            profile={
                "target_depth": {"quick": 0.4, "standard": 0.8, "deep": 1.0},
                "target_mode": {"report": 1.0, "custom": 0.8, "novel": 0.5},
                "parallel_bias": 0.3,
                "review_bias": 1.0,
                "evidence_bias": 1.0,
            },
        ),
        StrategyCandidate(
            strategy_id="balanced_flow",
            name="Balanced Flow",
            profile={
                "target_depth": {"quick": 0.8, "standard": 1.0, "deep": 0.8},
                "target_mode": {"report": 0.9, "custom": 1.0, "novel": 0.9},
                "parallel_bias": 0.7,
                "review_bias": 0.8,
                "evidence_bias": 0.8,
            },
        ),
        StrategyCandidate(
            strategy_id="evidence_intensive",
            name="Evidence Intensive",
            profile={
                "target_depth": {"quick": 0.3, "standard": 0.9, "deep": 1.0},
                "target_mode": {"report": 1.0, "custom": 0.9, "novel": 0.2},
                "parallel_bias": 0.4,
                "review_bias": 0.9,
                "evidence_bias": 1.2,
            },
        ),
        StrategyCandidate(
            strategy_id="chapter_parallel",
            name="Chapter Parallel",
            profile={
                "target_depth": {"quick": 0.7, "standard": 0.9, "deep": 0.9},
                "target_mode": {"report": 0.8, "custom": 0.9, "novel": 1.0},
                "parallel_bias": 1.2,
                "review_bias": 0.6,
                "evidence_bias": 0.6,
            },
        ),
        StrategyCandidate(
            strategy_id="fast_compact",
            name="Fast Compact",
            profile={
                "target_depth": {"quick": 1.2, "standard": 0.6, "deep": 0.3},
                "target_mode": {"report": 0.7, "custom": 0.8, "novel": 0.9},
                "parallel_bias": 0.8,
                "review_bias": 0.5,
                "evidence_bias": 0.4,
            },
        ),
    ]

