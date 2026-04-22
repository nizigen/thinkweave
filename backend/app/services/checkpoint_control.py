"""Shared helpers for task checkpoint/control normalization."""

from __future__ import annotations

from typing import Any


def normalize_checkpoint_data(
    checkpoint_data: dict[str, Any] | None,
    *,
    ensure_control_maps: bool = False,
) -> dict[str, Any]:
    """Return a normalized checkpoint payload with a valid ``control`` block."""
    checkpoint = dict(checkpoint_data) if isinstance(checkpoint_data, dict) else {}
    control = checkpoint.get("control")
    control_dict = dict(control) if isinstance(control, dict) else {}
    control_dict.setdefault("status", "active")

    if ensure_control_maps:
        preview_cache = control_dict.get("preview_cache")
        control_dict["preview_cache"] = (
            dict(preview_cache) if isinstance(preview_cache, dict) else {}
        )
        review_scores = control_dict.get("review_scores")
        control_dict["review_scores"] = (
            dict(review_scores) if isinstance(review_scores, dict) else {}
        )

    checkpoint["control"] = control_dict
    return checkpoint


def ensure_task_control(
    task: Any,
    *,
    ensure_control_maps: bool = False,
) -> dict[str, Any]:
    """Normalize and persist ``task.checkpoint_data`` in-place; return control."""
    checkpoint = normalize_checkpoint_data(
        getattr(task, "checkpoint_data", None),
        ensure_control_maps=ensure_control_maps,
    )
    task.checkpoint_data = checkpoint
    return checkpoint["control"]
