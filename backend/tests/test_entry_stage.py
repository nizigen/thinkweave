"""Tests for entry stage detection in mid-entry workflows."""

from app.services.entry_stage import EntryStage, build_entry_metadata, detect_entry_stage


def test_detect_entry_stage_title_only():
    assert detect_entry_stage() is EntryStage.INIT


def test_detect_entry_stage_with_draft_text():
    assert detect_entry_stage(draft_text="Draft body") is EntryStage.PRE_REVIEW_INTEGRITY


def test_detect_entry_stage_with_review_comments_only():
    assert (
        detect_entry_stage(review_comments="Please fix claim evidence.")
        is EntryStage.PRE_REVIEW_INTEGRITY
    )


def test_build_entry_metadata_flags_inputs():
    meta = build_entry_metadata(
        draft_text="Draft body",
        review_comments="Please revise references.",
    )
    assert meta["entry_stage"] == "pre_review_integrity"
    assert meta["entry_inputs"]["has_draft_text"] is True
    assert meta["entry_inputs"]["has_review_comments"] is True
