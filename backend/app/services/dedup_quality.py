"""Chapter dedup quality evaluation for long-text workflows."""

from __future__ import annotations

import math
import re
import uuid
from collections import Counter
from itertools import combinations
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.task_node import TaskNode

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


def _tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text)]


def _to_counter(text: str) -> Counter[str]:
    return Counter(_tokenize(text))


def _cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0

    shared = set(left) & set(right)
    dot = sum(left[token] * right[token] for token in shared)
    norm_left = math.sqrt(sum(v * v for v in left.values()))
    norm_right = math.sqrt(sum(v * v for v in right.values()))
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / (norm_left * norm_right)


def compute_dedup_quality(
    chapters: list[dict[str, Any]],
    *,
    threshold: float = 0.85,
    max_chars_per_chapter: int = 8000,
) -> dict[str, Any]:
    """Compute pairwise chapter similarity and duplicate rate."""
    normalized: list[dict[str, Any]] = []
    for chapter in chapters:
        content = str(chapter.get("content") or "").strip()
        if not content:
            continue
        bounded_content = content[:max_chars_per_chapter]
        normalized.append(
            {
                "node_id": str(chapter.get("node_id") or ""),
                "title": str(chapter.get("title") or ""),
                "content": bounded_content,
                "vector": _to_counter(bounded_content),
            }
        )

    pairs: list[dict[str, Any]] = []
    duplicate_pairs = 0
    for left, right in combinations(normalized, 2):
        similarity = _cosine_similarity(left["vector"], right["vector"])
        is_duplicate = similarity > threshold
        if is_duplicate:
            duplicate_pairs += 1
        pairs.append(
            {
                "left_node_id": left["node_id"],
                "right_node_id": right["node_id"],
                "left_title": left["title"],
                "right_title": right["title"],
                "similarity": round(similarity, 6),
                "duplicate": is_duplicate,
            }
        )

    pair_count = len(pairs)
    duplicate_rate = (duplicate_pairs / pair_count) if pair_count else 0.0
    return {
        "chapter_count": len(normalized),
        "pair_count": pair_count,
        "threshold": threshold,
        "duplicate_pairs": duplicate_pairs,
        "duplicate_rate": round(duplicate_rate, 6),
        "pairs": pairs,
    }


async def evaluate_dedup_quality(
    *,
    session: AsyncSession,
    task_id: uuid.UUID,
    threshold: float = 0.85,
    max_chapters: int = 32,
    max_chars_per_chapter: int = 8000,
) -> dict[str, Any]:
    """Evaluate chapter duplication quality for one task."""
    stmt = (
        select(TaskNode)
        .where(TaskNode.task_id == task_id)
        .where(TaskNode.agent_role == "writer")
        .where(TaskNode.result.is_not(None))
        .order_by(TaskNode.title, TaskNode.id)
        .limit(max_chapters)
    )
    result = await session.execute(stmt)
    nodes = list(result.scalars().all())

    report = compute_dedup_quality(
        [
            {
                "node_id": node.id,
                "title": node.title,
                "content": node.result or "",
            }
            for node in nodes
        ],
        threshold=threshold,
        max_chars_per_chapter=max_chars_per_chapter,
    )
    return {
        "task_id": str(task_id),
        **report,
    }


async def compare_dedup_quality(
    *,
    session: AsyncSession,
    baseline_task_id: uuid.UUID,
    candidate_task_id: uuid.UUID,
    user_id: str,
    is_admin: bool = False,
    goal_threshold: float = 0.05,
) -> dict[str, Any]:
    """Compare dedup quality reports for two tasks owned by the same user.

    IDOR prevention: both tasks must belong to ``user_id`` unless ``is_admin``
    is True.  On mismatch, a generic "Task not found" error is raised to avoid
    leaking the existence of other users' tasks.
    """
    baseline_task = await session.get(Task, baseline_task_id)
    if baseline_task is None:
        raise ValueError(f"Task {baseline_task_id} not found")
    candidate_task = await session.get(Task, candidate_task_id)
    if candidate_task is None:
        raise ValueError(f"Task {candidate_task_id} not found")

    baseline_owner = str(baseline_task.owner_id or "").strip()
    candidate_owner = str(candidate_task.owner_id or "").strip()
    if (baseline_owner != user_id or candidate_owner != user_id) and not is_admin:
        raise ValueError("Task not found")

    baseline_report = await evaluate_dedup_quality(
        session=session,
        task_id=baseline_task_id,
    )
    candidate_report = await evaluate_dedup_quality(
        session=session,
        task_id=candidate_task_id,
    )
    duplicate_rate_delta = (
        baseline_report["duplicate_rate"] - candidate_report["duplicate_rate"]
    )
    goal_met = duplicate_rate_delta >= goal_threshold
    return {
        "baseline_task_id": str(baseline_task_id),
        "candidate_task_id": str(candidate_task_id),
        "baseline_report": baseline_report,
        "candidate_report": candidate_report,
        "duplicate_rate_delta": round(duplicate_rate_delta, 6),
        "goal_threshold": goal_threshold,
        "goal_met": goal_met,
    }
