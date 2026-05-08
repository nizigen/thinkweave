"""MCTS-style UCB selector for execution strategy shadow ranking."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

from app.services.strategy_catalog import StrategyCandidate


@dataclass
class CandidateStats:
    visits: int = 0
    value_sum: float = 0.0

    @property
    def mean_value(self) -> float:
        if self.visits <= 0:
            return 0.0
        return self.value_sum / float(self.visits)


def _bound01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _estimate_reward(
    *,
    candidate: StrategyCandidate,
    mode: str,
    depth: str,
    target_words: int,
    random_jitter: float,
) -> float:
    profile = candidate.profile
    depth_score = float(profile.get("target_depth", {}).get(depth, 0.5))
    mode_score = float(profile.get("target_mode", {}).get(mode, 0.5))
    parallel_bias = float(profile.get("parallel_bias", 0.5))
    review_bias = float(profile.get("review_bias", 0.5))
    evidence_bias = float(profile.get("evidence_bias", 0.5))

    length_factor = min(1.0, max(0.0, float(target_words) / 30000.0))
    reward = (
        (depth_score * 0.28)
        + (mode_score * 0.22)
        + (parallel_bias * (0.12 + (0.18 * length_factor)))
        + (review_bias * 0.18)
        + (evidence_bias * 0.20)
    )
    reward += random_jitter
    return _bound01(reward)


def run_mcts_shadow(
    *,
    candidates: list[StrategyCandidate],
    mode: str,
    depth: str,
    target_words: int,
    ucb_c: float = 1.4,
    iterations: int = 32,
    seed_text: str = "",
) -> dict[str, Any]:
    if not candidates:
        return {
            "selected_strategy": None,
            "iterations": 0,
            "ucb_c": float(ucb_c),
            "candidates": [],
        }

    rng = random.Random(seed_text)
    stats: dict[str, CandidateStats] = {
        candidate.strategy_id: CandidateStats()
        for candidate in candidates
    }
    total_visits = 0

    # Warm-up: visit each candidate once to avoid division by zero.
    for candidate in candidates:
        jitter = rng.uniform(-0.03, 0.03)
        reward = _estimate_reward(
            candidate=candidate,
            mode=mode,
            depth=depth,
            target_words=target_words,
            random_jitter=jitter,
        )
        current = stats[candidate.strategy_id]
        current.visits += 1
        current.value_sum += reward
        total_visits += 1

    for _ in range(max(0, int(iterations) - len(candidates))):
        selected = candidates[0]
        best_ucb = -1.0
        for candidate in candidates:
            current = stats[candidate.strategy_id]
            if current.visits <= 0:
                score = 1e9
            else:
                score = current.mean_value + (
                    float(ucb_c) * math.sqrt(math.log(max(1, total_visits)) / current.visits)
                )
            if score > best_ucb:
                best_ucb = score
                selected = candidate

        jitter = rng.uniform(-0.03, 0.03)
        reward = _estimate_reward(
            candidate=selected,
            mode=mode,
            depth=depth,
            target_words=target_words,
            random_jitter=jitter,
        )
        current = stats[selected.strategy_id]
        current.visits += 1
        current.value_sum += reward
        total_visits += 1

    ranked = sorted(
        candidates,
        key=lambda candidate: (
            stats[candidate.strategy_id].mean_value,
            stats[candidate.strategy_id].visits,
        ),
        reverse=True,
    )
    selected = ranked[0]

    return {
        "selected_strategy": selected.strategy_id,
        "iterations": int(iterations),
        "ucb_c": float(ucb_c),
        "candidates": [
            {
                "strategy_id": candidate.strategy_id,
                "name": candidate.name,
                "visits": int(stats[candidate.strategy_id].visits),
                "mean_value": round(stats[candidate.strategy_id].mean_value, 6),
                "profile": dict(candidate.profile),
            }
            for candidate in ranked
        ],
    }

