"""Entry-stage detector for mid-entry long-text workflows."""

from __future__ import annotations

from enum import Enum
from typing import Any


class EntryStage(str, Enum):
    """Normalized entry stages for long-text workflow bootstrapping."""

    INIT = "init"
    PRE_REVIEW_INTEGRITY = "pre_review_integrity"


def detect_entry_stage(
    *,
    draft_text: str | None = None,
    review_comments: str | None = None,
) -> EntryStage:
    """Detect workflow entry stage from user-provided materials.

    Rules:
    - title-only requests start from INIT.
    - Any mid-entry material (draft or review comments) starts from
      PRE_REVIEW_INTEGRITY to enforce non-skippable integrity gates.
    """
    has_draft = bool((draft_text or "").strip())
    has_comments = bool((review_comments or "").strip())

    if has_draft or has_comments:
        return EntryStage.PRE_REVIEW_INTEGRITY
    return EntryStage.INIT


def build_entry_metadata(
    *,
    draft_text: str | None = None,
    review_comments: str | None = None,
) -> dict[str, Any]:
    """Build checkpoint metadata for observability and resume decisions."""
    stage = detect_entry_stage(
        draft_text=draft_text,
        review_comments=review_comments,
    )
    return {
        "entry_stage": stage.value,
        "entry_inputs": {
            "has_draft_text": bool((draft_text or "").strip()),
            "has_review_comments": bool((review_comments or "").strip()),
        },
    }
