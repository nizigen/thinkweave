"""Tests for TokenTracker — recording and aggregation."""

from app.utils.token_tracker import TokenTracker, UsageRecord


class TestUsageRecord:
    def test_defaults(self):
        rec = UsageRecord()
        assert rec.prompt_tokens == 0
        assert rec.call_count == 0

    def test_to_dict(self):
        rec = UsageRecord(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        d = rec.to_dict()
        assert d["prompt_tokens"] == 100
        assert d["total_tokens"] == 150
        assert "call_count" in d


class TestTokenTracker:
    def test_record_by_task(self):
        tracker = TokenTracker()
        tracker.record(
            prompt_tokens=100, completion_tokens=50, task_id="task-1"
        )
        tracker.record(
            prompt_tokens=200, completion_tokens=100, task_id="task-1"
        )

        usage = tracker.get_task_usage("task-1")
        assert usage.prompt_tokens == 300
        assert usage.completion_tokens == 150
        assert usage.total_tokens == 450
        assert usage.call_count == 2

    def test_record_by_role(self):
        tracker = TokenTracker()
        tracker.record(
            prompt_tokens=100, completion_tokens=50, role="writer"
        )
        tracker.record(
            prompt_tokens=80, completion_tokens=40, role="reviewer"
        )

        writer = tracker.get_role_usage("writer")
        assert writer.prompt_tokens == 100
        reviewer = tracker.get_role_usage("reviewer")
        assert reviewer.prompt_tokens == 80

    def test_record_both_task_and_role(self):
        tracker = TokenTracker()
        tracker.record(
            prompt_tokens=100,
            completion_tokens=50,
            task_id="task-1",
            role="writer",
        )

        assert tracker.get_task_usage("task-1").call_count == 1
        assert tracker.get_role_usage("writer").call_count == 1

    def test_cached_tokens(self):
        tracker = TokenTracker()
        tracker.record(
            prompt_tokens=100,
            completion_tokens=50,
            cached_tokens=60,
            task_id="task-1",
        )

        usage = tracker.get_task_usage("task-1")
        assert usage.cached_tokens == 60

    def test_unknown_task_returns_empty(self):
        tracker = TokenTracker()
        usage = tracker.get_task_usage("nonexistent")
        assert usage.total_tokens == 0
        assert usage.call_count == 0

    def test_get_summary(self):
        tracker = TokenTracker()
        tracker.record(
            prompt_tokens=100, completion_tokens=50,
            task_id="t1", role="writer",
        )

        summary = tracker.get_summary()
        assert "by_task" in summary
        assert "by_role" in summary
        assert "t1" in summary["by_task"]
        assert "writer" in summary["by_role"]

    def test_reset(self):
        tracker = TokenTracker()
        tracker.record(
            prompt_tokens=100, completion_tokens=50, task_id="t1"
        )
        tracker.reset()

        assert tracker.get_task_usage("t1").call_count == 0
        assert tracker.get_summary() == {"by_task": {}, "by_role": {}}

    def test_no_task_no_role_is_noop(self):
        tracker = TokenTracker()
        tracker.record(prompt_tokens=100, completion_tokens=50)
        assert tracker.get_summary() == {"by_task": {}, "by_role": {}}
