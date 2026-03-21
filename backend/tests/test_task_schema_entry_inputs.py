from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.task import TaskCreate


def test_task_create_accepts_reasonable_entry_inputs():
    task = TaskCreate(
        title="A valid task title for schema validation",
        draft_text="draft",
        review_comments="comments",
    )
    assert task.draft_text == "draft"
    assert task.review_comments == "comments"


def test_task_create_rejects_oversized_draft_text():
    with pytest.raises(ValidationError):
        TaskCreate(
            title="A valid task title for schema validation",
            draft_text="x" * 200_001,
        )


def test_task_create_rejects_oversized_review_comments():
    with pytest.raises(ValidationError):
        TaskCreate(
            title="A valid task title for schema validation",
            review_comments="x" * 50_001,
        )
