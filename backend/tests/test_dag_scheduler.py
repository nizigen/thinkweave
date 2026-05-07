"""Tests for DAG Scheduler — dag_scheduler.py

测试策略：
  - 使用 fakeredis 替代真实 Redis
  - 使用 SQLite async 替代 PostgreSQL（单元测试不需要真实 DB）
  - Mock communicator 发送，只验证调度逻辑
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.config import settings
from app.services.node_schema import coerce_output_to_role_schema
from app.services.writer_pool import WriterPool
from app.services.dag_scheduler import (
    AGENT_BUSY,
    AGENT_IDLE,
    MAX_RETRIES,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_READY,
    STATUS_RUNNING,
    STATUS_SKIPPED,
    DAGScheduler,
    get_scheduler,
    start_scheduler,
    stop_scheduler,
    _is_invalid_output_for_role,
    _is_suspicious_node_output,
    _active_schedulers,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_uuid() -> uuid.UUID:
    return uuid.uuid4()


class FakeNode:
    """模拟 TaskNode ORM 对象。"""

    def __init__(
        self,
        node_id: uuid.UUID | None = None,
        task_id: uuid.UUID | None = None,
        title: str = "test node",
        agent_role: str = "writer",
        status: str = STATUS_PENDING,
        depends_on: list[uuid.UUID] | None = None,
        retry_count: int = 0,
        assigned_agent: uuid.UUID | None = None,
    ):
        self.id = node_id or make_uuid()
        self.task_id = task_id or make_uuid()
        self.title = title
        self.agent_role = agent_role
        self.status = status
        self.depends_on = depends_on
        self.retry_count = retry_count
        self.assigned_agent = assigned_agent
        self.result = None
        self.started_at = None
        self.finished_at = None


class FakeAgent:
    """模拟 Agent ORM 对象。"""

    def __init__(
        self,
        agent_id: uuid.UUID | None = None,
        name: str = "test-agent",
        role: str = "writer",
        status: str = AGENT_IDLE,
        capabilities: str | None = None,
    ):
        self.id = agent_id or make_uuid()
        self.name = name
        self.role = role
        self.status = status
        self.capabilities = capabilities
        self.created_at = datetime.now(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def task_id() -> uuid.UUID:
    return make_uuid()


@pytest.fixture
def scheduler(task_id: uuid.UUID) -> DAGScheduler:
    return DAGScheduler(task_id)


# ---------------------------------------------------------------------------
# Test: 基础属性
# ---------------------------------------------------------------------------


class TestDAGSchedulerInit:
    def test_init_sets_task_id(self, task_id: uuid.UUID):
        s = DAGScheduler(task_id)
        assert s.task_id == task_id

    def test_init_empty_running_nodes(self, scheduler: DAGScheduler):
        assert scheduler._running_nodes == {}

    def test_stop_sets_event(self, scheduler: DAGScheduler):
        assert not scheduler._stop.is_set()
        scheduler.stop()
        assert scheduler._stop.is_set()


class TestWriterPool:
    def test_writer_pool_enforces_concurrent_slots(self):
        pool = WriterPool(
            max_concurrent_writers=2,
            max_tokens_per_minute=10000,
            max_requests_per_minute=100,
        )
        assert pool.acquire(node_id="n1", estimated_tokens=100)[0] is True
        assert pool.acquire(node_id="n2", estimated_tokens=100)[0] is True
        ok, reason = pool.acquire(node_id="n3", estimated_tokens=100)
        assert ok is False
        assert reason == "concurrency_exceeded"

    def test_writer_pool_enforces_request_budget(self):
        pool = WriterPool(
            max_concurrent_writers=5,
            max_tokens_per_minute=10000,
            max_requests_per_minute=2,
        )
        assert pool.acquire(node_id="n1", estimated_tokens=100)[0] is True
        assert pool.acquire(node_id="n2", estimated_tokens=100)[0] is True
        pool.release(node_id="n1")
        pool.release(node_id="n2")
        ok, reason = pool.acquire(node_id="n3", estimated_tokens=100)
        assert ok is False
        assert reason == "request_budget_exceeded"

    def test_writer_pool_enforces_token_budget(self):
        pool = WriterPool(
            max_concurrent_writers=5,
            max_tokens_per_minute=100,
            max_requests_per_minute=100,
        )
        assert pool.acquire(node_id="n1", estimated_tokens=80)[0] is True
        pool.release(node_id="n1")
        ok, reason = pool.acquire(node_id="n2", estimated_tokens=30)
        assert ok is False
        assert reason == "token_budget_exceeded"

    def test_writer_pool_budget_recovers_after_time_window(self):
        now = 1000.0

        def _clock():
            return now

        pool = WriterPool(
            max_concurrent_writers=5,
            max_tokens_per_minute=100,
            max_requests_per_minute=1,
            clock=_clock,
        )
        assert pool.acquire(node_id="n1", estimated_tokens=80)[0] is True
        pool.release(node_id="n1")
        ok, _ = pool.acquire(node_id="n2", estimated_tokens=10)
        assert ok is False

        now += 61.0
        ok2, reason2 = pool.acquire(node_id="n3", estimated_tokens=10)
        assert ok2 is True
        assert reason2 in {"acquired", "already_acquired"}


class TestRoleOutputValidation:
    def test_writer_rejects_reviewer_json(self):
        payload = """{"score": 81, "must_fix": [], "feedback": "ok", "pass": true}"""
        assert _is_invalid_output_for_role("writer", payload) is True

    def test_writer_rejects_consistency_json(self):
        payload = """{"pass": false, "style_conflicts": [], "claim_conflicts": [], "repair_targets": []}"""
        assert _is_invalid_output_for_role("writer", payload) is True

    def test_writer_rejects_plain_markdown(self):
        content = "# Chapter 1\n\nThis is valid markdown chapter content."
        assert _is_invalid_output_for_role("writer", content) is True

    def test_writer_accepts_structured_writer_json(self):
        payload = (
            '{"chapter_title":"第1章","content_markdown":"# 第1章\\n\\n'
            '这是一个满足长度要求的章节正文示例，用于验证 writer 结构化输出契约。'
            '内容保持在本章范围内，并且避免模板化短语，确保质量门槛可通过。",'
            '"key_points":["k1"],"evidence_trace":[],"boundary_notes":[]}'
        )
        assert _is_invalid_output_for_role("writer", payload) is False

    def test_writer_schema_check_does_not_fail_on_style_only_issues(self):
        payload = (
            '{"chapter_title":"第1章","content_markdown":"首先，这里给出背景。\\n\\n'
            '其次，这里给出方法。\\n\\n最后，这里给出结论。",'
            '"key_points":["k1"],"evidence_trace":[],"boundary_notes":[]}'
        )
        assert _is_invalid_output_for_role("writer", payload) is False

    def test_reviewer_requires_json_contract(self):
        assert _is_invalid_output_for_role("reviewer", "plain text") is True
        assert _is_invalid_output_for_role(
            "reviewer",
            """{"score": 75, "must_fix": [], "feedback": "ok", "pass": true}""",
        ) is False

    def test_consistency_requires_json_contract(self):
        assert _is_invalid_output_for_role("consistency", "plain text") is True
        assert _is_invalid_output_for_role(
            "consistency",
            """{"pass": false, "style_conflicts": [], "claim_conflicts": [], "repair_targets": [], "repair_priority": [1], "severity_summary": {"critical":0,"high":1,"medium":0,"low":0}}""",
        ) is False


class TestRoleOutputCoercion:
    def test_writer_plain_markdown_can_be_coerced_into_writer_schema(self):
        raw = "# 第1章\n\n这是未结构化的 writer 草稿正文。"
        repaired = coerce_output_to_role_schema("writer", raw, node_title="第1章：背景")
        assert isinstance(repaired, str) and repaired.strip()
        assert _is_invalid_output_for_role("writer", repaired) is False

    def test_reviewer_plain_text_can_be_coerced_into_reviewer_schema(self):
        raw = "这一章质量一般，需要补证据。"
        repaired = coerce_output_to_role_schema("reviewer", raw, node_title="第2章审查")
        assert isinstance(repaired, str) and repaired.strip()
        assert _is_invalid_output_for_role("reviewer", repaired) is False


# ---------------------------------------------------------------------------
# Test: 并发控制 _can_dispatch
# ---------------------------------------------------------------------------


class TestCanDispatch:
    def test_allows_when_under_limit(self, scheduler: DAGScheduler):
        assert scheduler._can_dispatch("writer") is True

    def test_blocks_when_llm_limit_reached(self, scheduler: DAGScheduler):
        # 填满 LLM 并发槽
        for _ in range(settings.max_concurrent_llm_calls):
            nid = make_uuid()
            scheduler._running_nodes[nid] = make_uuid()
        assert scheduler._can_dispatch("writer") is False

    def test_blocks_writer_when_writer_limit_reached(self, scheduler: DAGScheduler):
        # 填满 writer 并发槽
        for _ in range(settings.max_concurrent_writers):
            nid = make_uuid()
            scheduler._running_nodes[nid] = make_uuid()
            scheduler._node_roles[nid] = "writer"
        # 总 LLM 并发未满，但 writer 已满
        assert scheduler._can_dispatch("writer") is False
        # 其他角色仍可调度
        assert scheduler._can_dispatch("reviewer") is True

    def test_allows_non_writer_even_when_writers_full(self, scheduler: DAGScheduler):
        for _ in range(settings.max_concurrent_writers):
            nid = make_uuid()
            scheduler._running_nodes[nid] = make_uuid()
            scheduler._node_roles[nid] = "writer"
        assert scheduler._can_dispatch("outline") is True


class TestOrphanRunningRecovery:
    @pytest.mark.asyncio
    async def test_reconcile_orphan_running_nodes_recovers_to_ready(
        self,
        scheduler: DAGScheduler,
    ):
        agent_id = make_uuid()
        stale_node = FakeNode(
            task_id=scheduler.task_id,
            status=STATUS_RUNNING,
            retry_count=2,
            assigned_agent=agent_id,
        )

        first_result = MagicMock()
        first_result.scalars.return_value.all.return_value = [stale_node]

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock) as mock_set_status,
            patch("app.services.dag_scheduler.push_ready_node", new_callable=AsyncMock) as mock_push_ready,
        ):
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(side_effect=[first_result, MagicMock(), MagicMock()])
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler._reconcile_orphan_running_nodes()

        mock_session.commit.assert_awaited_once()
        mock_set_status.assert_awaited_once_with(
            scheduler.task_id,
            str(stale_node.id),
            STATUS_READY,
        )
        mock_push_ready.assert_awaited_once_with(str(stale_node.id), priority=2.0)

class TestWriterBudgetHelpers:
    def test_parse_chapter_meta_supports_english_titles(self, scheduler: DAGScheduler):
        idx, name = scheduler._parse_chapter_meta("Chapter 2: Method and Analysis")
        assert idx == 2
        assert "Method" in name

        idx2, _ = scheduler._parse_chapter_meta("Ch. 3 - Results")
        assert idx2 == 3

    def test_parse_chapter_meta_supports_chinese_numeral_titles(self, scheduler: DAGScheduler):
        idx, name = scheduler._parse_chapter_meta("第一章：背景与问题定义")
        assert idx == 1
        assert "背景" in name

        idx2, name2 = scheduler._parse_chapter_meta("第十二章：实施路径")
        assert idx2 == 12
        assert "实施路径" in name2

    def test_primary_writer_count_excludes_expansion_titles(self, scheduler: DAGScheduler):
        writer_nodes = [
            ("第1章：背景", "content-a"),
            ("第1章：背景（扩写）", "content-b"),
            ("第2章：方法", "content-c"),
            ("全稿扩写与篇幅补足", "content-d"),
        ]
        assert scheduler._primary_writer_count(writer_nodes) == 2

    def test_expansion_title_detection(self, scheduler: DAGScheduler):
        assert scheduler._is_expansion_writer_title("第3章：实验（扩写）") is True
        assert scheduler._is_expansion_writer_title("全稿扩写与篇幅补足") is True
        assert scheduler._is_expansion_writer_title("术语整合与口径统一") is False
        assert scheduler._is_expansion_writer_title("第3章：实验设计") is False

    @pytest.mark.asyncio
    async def test_build_assignment_payload_includes_word_budget_and_ledger(
        self,
        scheduler: DAGScheduler,
    ):
        node_id = make_uuid()
        task = SimpleNamespace(
            title="Longform strategy report",
            mode="report",
            depth="deep",
            target_words=30000,
            checkpoint_data={},
        )
        session = AsyncMock()
        session.get = AsyncMock(return_value=task)

        with (
            patch.object(scheduler, "_load_outline_result", new=AsyncMock(return_value="")),
            patch.object(
                scheduler,
                "_load_writer_nodes",
                new=AsyncMock(return_value=[("第1章：背景", "a"), ("第2章：方法", "b")]),
            ),
        ):
            payload = await scheduler._build_assignment_payload(
                session=session,
                node_id=node_id,
                node_title="第1章：背景",
                node_role="writer",
                node_retry_count=0,
                routing_reason="role_fallback",
                routing_mode="auto",
            )

        assert payload["planned_words"] > 0
        assert payload["word_floor"] >= 300
        assert payload["word_ceiling"] >= payload["word_floor"]
        assert payload["task_target_words"] == 30000
        assert payload["node_target_words"] == payload["planned_words"]
        assert payload["target_words"] == payload["planned_words"]
        ledger = task.checkpoint_data.get("node_budget_ledger", {})
        assert str(node_id) in ledger
        assert ledger[str(node_id)]["planned_words"] == payload["planned_words"]

    @pytest.mark.asyncio
    async def test_writer_min_units_prefers_node_budget_ledger_floor(
        self,
        scheduler: DAGScheduler,
    ):
        node_id = make_uuid()
        task = SimpleNamespace(
            target_words=30000,
            checkpoint_data={
                "node_budget_ledger": {
                    str(node_id): {
                        "word_floor": 1333,
                    }
                }
            },
        )
        session = AsyncMock()
        session.get = AsyncMock(return_value=task)

        min_units = await scheduler._writer_min_units_for_task(
            session=session,
            node_id=node_id,
            node_title="第1章：背景",
        )
        assert min_units == 1333

    @pytest.mark.asyncio
    async def test_auto_expansion_records_adaptive_decision(
        self,
        scheduler: DAGScheduler,
    ):
        task = SimpleNamespace(checkpoint_data={})
        session = AsyncMock()
        wave_rows = MagicMock()
        wave_rows.all.return_value = []
        chapter_rows = MagicMock()
        chapter_rows.all.return_value = [
            (
                "第1章：背景",
                '{"chapter_title":"第1章：背景","content_markdown":"第一章正文较短。","paragraphs":[{"text":"第一章正文较短。","citation_keys":[]}]}',
            ),
            (
                "第2章：方法",
                '{"chapter_title":"第2章：方法","content_markdown":"第二章正文较长一些。第二章正文较长一些。","paragraphs":[{"text":"第二章正文较长一些。第二章正文较长一些。","citation_keys":[]}]}',
            ),
        ]
        session.execute = AsyncMock(side_effect=[wave_rows, chapter_rows])
        session.get = AsyncMock(return_value=task)
        session.add = MagicMock()
        session.flush = AsyncMock()

        with (
            patch("app.services.dag_scheduler.set_dag_node_status", new=AsyncMock()),
            patch("app.services.dag_scheduler.push_ready_node", new=AsyncMock()),
        ):
            created = await scheduler._enqueue_auto_expansion_wave(
                session=session,
                target_words=30000,
                current_words=12000,
            )

        assert created is True
        decisions = task.checkpoint_data.get("expansion_decisions", [])
        assert decisions
        latest = decisions[-1]
        assert latest["gap"] == 18000
        assert latest["expansion_nodes"] >= 1
        assert "adaptive expansion" in latest["reason"]

    @pytest.mark.asyncio
    async def test_auto_expansion_prefers_chapter_target_nodes_when_chapters_exist(
        self,
        scheduler: DAGScheduler,
    ):
        task = SimpleNamespace(checkpoint_data={})
        session = AsyncMock()
        wave_rows = MagicMock()
        wave_rows.all.return_value = []
        chapter_rows = MagicMock()
        chapter_rows.all.return_value = [
            ("第1章：背景", '{"chapter_title":"第1章：背景","content_markdown":"第一章正文。","paragraphs":[{"text":"第一章正文。","citation_keys":[]}]}'),
            ("第2章：方法", '{"chapter_title":"第2章：方法","content_markdown":"第二章正文更长一些。第二章正文更长一些。","paragraphs":[{"text":"第二章正文更长一些。第二章正文更长一些。","citation_keys":[]}]}'),
        ]
        session.execute = AsyncMock(side_effect=[wave_rows, chapter_rows])
        session.get = AsyncMock(return_value=task)
        session.add = MagicMock()
        session.flush = AsyncMock()

        with (
            patch("app.services.dag_scheduler.set_dag_node_status", new=AsyncMock()),
            patch("app.services.dag_scheduler.push_ready_node", new=AsyncMock()),
        ):
            created = await scheduler._enqueue_auto_expansion_wave(
                session=session,
                target_words=20000,
                current_words=8000,
            )

        assert created is True
        titles = [
            str(call.args[0].title)
            for call in session.add.call_args_list
        ]
        assert any(title.startswith("第1章：自动补写轮次1") for title in titles)

    @pytest.mark.asyncio
    async def test_auto_expansion_skips_when_no_chapter_candidates(
        self,
        scheduler: DAGScheduler,
    ):
        task = SimpleNamespace(checkpoint_data={})
        session = AsyncMock()
        wave_rows = MagicMock()
        wave_rows.all.return_value = []
        chapter_rows = MagicMock()
        chapter_rows.all.return_value = [
            ("全稿扩写建议", '{"content_markdown":"无章节编号正文"}'),
        ]
        session.execute = AsyncMock(side_effect=[wave_rows, chapter_rows])
        session.get = AsyncMock(return_value=task)
        session.add = MagicMock()
        session.flush = AsyncMock()

        with (
            patch("app.services.dag_scheduler.set_dag_node_status", new=AsyncMock()),
            patch("app.services.dag_scheduler.push_ready_node", new=AsyncMock()),
        ):
            created = await scheduler._enqueue_auto_expansion_wave(
                session=session,
                target_words=10000,
                current_words=7000,
            )

        assert created is False
        assert session.add.call_count == 0

    @pytest.mark.asyncio
    async def test_assembly_editor_wave_disabled_for_quick_depth(
        self,
        scheduler: DAGScheduler,
    ):
        task = SimpleNamespace(depth="quick", target_words=1000, checkpoint_data={})
        session = AsyncMock()
        session.get = AsyncMock(return_value=task)
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        created = await scheduler._ensure_assembly_editor_wave(session=session)
        assert created is False
        assert session.execute.await_count == 0
        assert session.add.call_count == 0

    @pytest.mark.asyncio
    async def test_assembly_editor_wave_disabled_by_env_flag(
        self,
        scheduler: DAGScheduler,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("ENABLE_ASSEMBLY_EDITOR_WAVE", "false")
        task = SimpleNamespace(depth="standard", target_words=10000, checkpoint_data={})
        session = AsyncMock()
        session.get = AsyncMock(return_value=task)
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()

        created = await scheduler._ensure_assembly_editor_wave(session=session)
        assert created is False
        assert session.execute.await_count == 0
        assert session.add.call_count == 0

    @pytest.mark.asyncio
    async def test_allow_auto_expansion_enabled_for_quick_depth_with_one_primary_chapter(
        self,
        scheduler: DAGScheduler,
    ):
        long_text = "第一章正文充分，满足基本可用长度。" * 80
        writer_payload = json.dumps(
            {
                "chapter_title": "第1章：背景",
                "content_markdown": long_text,
                "paragraphs": [{"text": long_text, "citation_keys": []}],
            },
            ensure_ascii=False,
        )
        rows = MagicMock()
        rows.all.return_value = [
            (
                "第1章：背景",
                writer_payload,
                "done",
            ),
        ]
        session = AsyncMock()
        session.execute = AsyncMock(return_value=rows)
        with patch.object(settings, "enable_finalize_auto_expansion", True):
            allowed, reason = await scheduler._allow_auto_expansion_after_finalize(
                session=session,
                task=None,
                target_words=1800,
                current_words=1200,
                depth="quick",
            )
        assert allowed is True
        assert reason == "ok"

    @pytest.mark.asyncio
    async def test_allow_auto_expansion_disabled_by_policy_flag(
        self,
        scheduler: DAGScheduler,
    ):
        session = AsyncMock()
        with patch.object(settings, "enable_finalize_auto_expansion", False):
            allowed, reason = await scheduler._allow_auto_expansion_after_finalize(
                session=session,
                task=None,
                target_words=1800,
                current_words=1200,
                depth="standard",
            )
        assert allowed is False
        assert reason == "disabled_by_policy"

    @pytest.mark.asyncio
    async def test_allow_auto_expansion_disabled_when_no_usable_output(
        self,
        scheduler: DAGScheduler,
    ):
        session = AsyncMock()
        with patch.object(settings, "enable_finalize_auto_expansion", True):
            allowed, reason = await scheduler._allow_auto_expansion_after_finalize(
                session=session,
                task=None,
                target_words=1800,
                current_words=0,
                depth="standard",
            )
        assert allowed is False
        assert reason == "no_usable_output"

    @pytest.mark.asyncio
    async def test_allow_auto_expansion_requires_multiple_primary_chapters(
        self,
        scheduler: DAGScheduler,
    ):
        session = AsyncMock()
        rows = MagicMock()
        rows.all.return_value = [
            (
                "第1章：背景",
                '{"chapter_title":"第1章：背景","content_markdown":"一段较短内容","paragraphs":[{"text":"一段较短内容","citation_keys":[]}]}',
                "done",
            ),
        ]
        session.execute = AsyncMock(return_value=rows)
        with patch.object(settings, "enable_finalize_auto_expansion", True):
            allowed, reason = await scheduler._allow_auto_expansion_after_finalize(
                session=session,
                task=None,
                target_words=10000,
                current_words=7000,
                depth="standard",
            )
        assert allowed is False
        assert reason == "insufficient_primary_chapters"


class TestConsistencyRepairBudget:
    def test_consistency_actionable_detection_false_when_empty(self, scheduler: DAGScheduler):
        parsed = {
            "style_conflicts": [],
            "claim_conflicts": [],
            "duplicate_coverage": [],
            "term_inconsistency": [],
            "transition_gaps": [],
            "source_policy_violations": [],
            "repair_targets": [],
            "repair_priority": [],
            "severity_summary": {"critical": 0, "high": 0, "medium": 0, "low": 0},
        }
        assert scheduler._consistency_has_actionable_issues(parsed) is False

    def test_consistency_actionable_detection_false_with_medium_only_conflict(
        self,
        scheduler: DAGScheduler,
    ):
        parsed = {
            "claim_conflicts": [{"chapter_index": 1, "severity": "medium"}],
            "repair_targets": [],
            "repair_priority": [],
            "severity_summary": {"critical": 0, "high": 0, "medium": 1, "low": 0},
        }
        assert scheduler._consistency_has_actionable_issues(parsed) is False

    def test_consistency_actionable_detection_true_with_unapplied_recommendations(
        self,
        scheduler: DAGScheduler,
    ):
        parsed = {
            "unapplied_recommendations": [{"chapter_index": 6, "severity": "high"}],
            "repair_targets": [],
            "repair_priority": [],
            "severity_summary": {"critical": 0, "high": 1, "medium": 0, "low": 0},
        }
        assert scheduler._consistency_has_actionable_issues(parsed) is True

    @pytest.mark.asyncio
    async def test_consume_repair_budget_allows_within_quota(
        self,
        scheduler: DAGScheduler,
    ):
        task = SimpleNamespace(
            target_words=30000,
            checkpoint_data={},
        )
        session = AsyncMock()
        session.get = AsyncMock(return_value=task)
        parsed = {
            "style_conflicts": [{"chapter_index": 2, "severity": "medium"}],
            "claim_conflicts": [{"chapter_index": 3, "severity": "high"}],
            "repair_priority": [3, 2],
            "repair_targets": [2, 3],
            "severity_summary": {"critical": 0, "high": 1, "medium": 1, "low": 0},
        }

        allowed, targets, report = await scheduler._consume_consistency_repair_budget(
            session=session,
            parsed=parsed,
            fallback_targets=[2],
        )

        assert allowed is True
        assert 3 in targets
        assert report is not None
        budget = task.checkpoint_data.get("consistency_repair_budget", {})
        assert budget.get("remaining_points", 0) < budget.get("total_points", 0)

    @pytest.mark.asyncio
    async def test_consume_repair_budget_rejects_when_exhausted(
        self,
        scheduler: DAGScheduler,
    ):
        task = SimpleNamespace(
            target_words=30000,
            checkpoint_data={
                "consistency_repair_budget": {
                    "total_points": 4,
                    "remaining_points": 1,
                    "spent_points": 3,
                    "rounds": 1,
                    "events": [],
                }
            },
        )
        session = AsyncMock()
        session.get = AsyncMock(return_value=task)
        parsed = {
            "claim_conflicts": [{"chapter_index": 3, "severity": "high"}],
            "repair_priority": [3],
            "repair_targets": [3],
            "severity_summary": {"critical": 0, "high": 1, "medium": 0, "low": 0},
        }

        allowed, targets, report = await scheduler._consume_consistency_repair_budget(
            session=session,
            parsed=parsed,
            fallback_targets=[3],
        )

        assert allowed is False
        assert targets == [3]
        assert report is not None
        assert report["required_points"] > report["remaining_points_before"]


class TestDrainTaskResultShapeRepair:
    @pytest.mark.asyncio
    async def test_drain_task_results_auto_repairs_invalid_writer_shape(
        self,
        scheduler: DAGScheduler,
    ):
        node_id = make_uuid()
        agent_id = make_uuid()
        envelope = SimpleNamespace(
            msg_type="task_result",
            node_id=str(node_id),
            from_agent=str(agent_id),
            payload={
                "status": "done",
                "output": "# 第1章\n\n这是未结构化的 writer 草稿。",
            },
        )

        with (
            patch(
                "app.services.dag_scheduler.xread_latest",
                new_callable=AsyncMock,
                return_value=[SimpleNamespace(message_id="1-0", data={})],
            ),
            patch(
                "app.services.dag_scheduler.MessageEnvelope.from_redis",
                return_value=envelope,
            ),
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch.object(
                scheduler,
                "_validate_writer_output_length",
                new_callable=AsyncMock,
                return_value=(True, 600, 300),
            ),
            patch.object(
                scheduler,
                "on_node_completed",
                new_callable=AsyncMock,
            ) as mock_completed,
            patch.object(
                scheduler,
                "on_node_failed",
                new_callable=AsyncMock,
            ) as mock_failed,
        ):
            mock_session = AsyncMock()
            role_row = MagicMock()
            role_row.first.return_value = ("writer", "第1章：背景", 0)
            mock_session.execute = AsyncMock(return_value=role_row)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler._drain_task_results()

        mock_completed.assert_awaited_once()
        completed_output = mock_completed.await_args.kwargs.get("result", "")
        assert _is_invalid_output_for_role("writer", completed_output) is False
        mock_failed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_drain_task_results_forces_writer_fallback_when_coerce_still_invalid(
        self,
        scheduler: DAGScheduler,
    ):
        node_id = make_uuid()
        agent_id = make_uuid()
        envelope = SimpleNamespace(
            msg_type="task_result",
            node_id=str(node_id),
            from_agent=str(agent_id),
            payload={
                "status": "done",
                "output": '{"unexpected":"shape"}',
            },
        )

        with (
            patch(
                "app.services.dag_scheduler.xread_latest",
                new_callable=AsyncMock,
                return_value=[SimpleNamespace(message_id="1-0", data={})],
            ),
            patch(
                "app.services.dag_scheduler.MessageEnvelope.from_redis",
                return_value=envelope,
            ),
            patch(
                "app.services.dag_scheduler.coerce_output_to_role_schema",
                return_value='{"still":"invalid"}',
            ),
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch.object(
                scheduler,
                "_validate_writer_output_length",
                new_callable=AsyncMock,
                return_value=(True, 600, 300),
            ),
            patch.object(
                scheduler,
                "on_node_completed",
                new_callable=AsyncMock,
            ) as mock_completed,
            patch.object(
                scheduler,
                "on_node_failed",
                new_callable=AsyncMock,
            ) as mock_failed,
        ):
            mock_session = AsyncMock()
            role_row = MagicMock()
            role_row.first.return_value = ("writer", "终稿扩写与整合", 0)
            mock_session.execute = AsyncMock(return_value=role_row)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler._drain_task_results()

        mock_completed.assert_awaited_once()
        completed_output = str(mock_completed.await_args.kwargs.get("result", ""))
        assert _is_invalid_output_for_role("writer", completed_output) is False
        assert "content_markdown" in completed_output
        mock_failed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_drain_task_results_passes_block_ms_to_stream_read(
        self,
        scheduler: DAGScheduler,
    ) -> None:
        with patch(
            "app.services.dag_scheduler.xread_latest",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_xread:
            consumed = await scheduler._drain_task_results(block_ms=987)

        assert consumed == 0
        mock_xread.assert_awaited_once()
        assert mock_xread.await_args.kwargs["block"] == 987


class TestEventDrivenWait:
    @pytest.mark.asyncio
    async def test_wait_for_next_signal_prefers_stream_event_path(
        self,
        scheduler: DAGScheduler,
    ) -> None:
        scheduler._schedule_event.clear()
        with (
            patch.object(
                scheduler,
                "_drain_task_results",
                new=AsyncMock(return_value=1),
            ) as mock_drain,
            patch.object(
                scheduler._schedule_event,
                "wait",
                new=AsyncMock(return_value=True),
            ) as mock_wait,
        ):
            await scheduler._wait_for_next_signal()

        mock_drain.assert_awaited_once_with(block_ms=1000)
        mock_wait.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_wait_for_next_signal_short_circuits_when_schedule_event_already_set(
        self,
        scheduler: DAGScheduler,
    ) -> None:
        scheduler._schedule_event.set()
        with (
            patch.object(
                scheduler,
                "_drain_task_results",
                new=AsyncMock(return_value=1),
            ) as mock_drain,
        ):
            await scheduler._wait_for_next_signal()

        mock_drain.assert_not_awaited()


class TestMatchAgentRouting:
    @pytest.mark.asyncio
    async def test_match_agent_prefers_capability_match_over_plain_role(
        self,
        scheduler: DAGScheduler,
    ):
        role_only = FakeAgent(name="role-only", role="writer", capabilities="draft")
        capability_agent = FakeAgent(
            name="cap-agent",
            role="writer",
            capabilities="draft,retrieval",
        )
        fake_result = MagicMock()
        fake_result.scalars.return_value.all.return_value = [role_only, capability_agent]
        session = AsyncMock()
        session.execute = AsyncMock(return_value=fake_result)

        agent, reason = await scheduler._match_agent(
            session,
            role="writer",
            required_capabilities=["retrieval"],
            preferred_agents=[],
            routing_mode="auto",
        )

        assert agent is capability_agent
        assert reason == "capability_match"

    @pytest.mark.asyncio
    async def test_match_agent_falls_back_to_role_when_capability_missing(
        self,
        scheduler: DAGScheduler,
    ):
        role_agent = FakeAgent(name="writer-a", role="writer", capabilities="draft")
        fake_result = MagicMock()
        fake_result.scalars.return_value.all.return_value = [role_agent]
        session = AsyncMock()
        session.execute = AsyncMock(return_value=fake_result)

        agent, reason = await scheduler._match_agent(
            session,
            role="writer",
            required_capabilities=["retrieval"],
            preferred_agents=[],
            routing_mode="auto",
        )

        assert agent is role_agent
        assert reason == "role_fallback"

    @pytest.mark.asyncio
    async def test_match_agent_strict_bind_blocks_fallback(
        self,
        scheduler: DAGScheduler,
    ):
        role_agent = FakeAgent(name="writer-a", role="writer", capabilities="draft")
        fake_result = MagicMock()
        fake_result.scalars.return_value.all.return_value = [role_agent]
        session = AsyncMock()
        session.execute = AsyncMock(return_value=fake_result)

        agent, reason = await scheduler._match_agent(
            session,
            role="writer",
            required_capabilities=["retrieval"],
            preferred_agents=["missing-agent"],
            routing_mode="strict_bind",
        )

        assert agent is None
        assert reason == "strict_bind_no_match"


class TestAssignNode:
    @pytest.mark.asyncio
    async def test_assign_node_commits_before_publishing_external_side_effects(
        self,
        scheduler: DAGScheduler,
    ):
        node = FakeNode(status=STATUS_READY, retry_count=0, agent_role="writer")
        agent = FakeAgent(role="writer")
        session = AsyncMock()
        event_order: list[str] = []
        session.expire_all = MagicMock()

        async def record_commit() -> None:
            event_order.append("commit")

        async def record_assignment(**_: object) -> None:
            event_order.append("task_assign")

        async def record_status(**_: object) -> None:
            event_order.append("status_update")

        session.commit = AsyncMock(side_effect=record_commit)
        session.get = AsyncMock(
            side_effect=[
                FakeNode(
                    node_id=node.id,
                    status=STATUS_RUNNING,
                    assigned_agent=agent.id,
                    agent_role="writer",
                ),
                SimpleNamespace(checkpoint_data={"control": {"status": "active"}}),
            ]
        )

        update_result = MagicMock()
        update_result.rowcount = 1
        session.execute = AsyncMock(side_effect=[update_result, MagicMock()])

        with (
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock),
            patch("app.services.dag_scheduler.add_timeout_watch", new_callable=AsyncMock),
            patch("app.services.dag_scheduler.communicator") as mock_comm,
        ):
            mock_comm.send_task_assignment = AsyncMock(side_effect=record_assignment)
            mock_comm.send_status_update = AsyncMock(side_effect=record_status)

            await scheduler._assign_node(session, node, agent)

        assert event_order[:2] == ["commit", "task_assign"]

    @pytest.mark.asyncio
    async def test_assign_node_aborts_if_node_is_skipped_before_side_effects(
        self,
        scheduler: DAGScheduler,
    ):
        node = FakeNode(status=STATUS_READY, retry_count=0, agent_role="writer")
        agent = FakeAgent(role="writer")
        session = AsyncMock()
        session.expire_all = MagicMock()
        skipped_node = FakeNode(
            node_id=node.id,
            status=STATUS_SKIPPED,
            assigned_agent=None,
        )
        session.get = AsyncMock(
            side_effect=[
                skipped_node,
                SimpleNamespace(checkpoint_data={"control": {"status": "active"}}),
            ]
        )
        update_result = MagicMock()
        update_result.rowcount = 1
        session.execute = AsyncMock(side_effect=[update_result, MagicMock(), MagicMock(), MagicMock()])

        with (
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock) as mock_set_status,
            patch("app.services.dag_scheduler.add_timeout_watch", new_callable=AsyncMock) as mock_timeout,
            patch("app.services.dag_scheduler.communicator") as mock_comm,
        ):
            mock_comm.send_task_assignment = AsyncMock()
            mock_comm.send_status_update = AsyncMock()

            await scheduler._assign_node(session, node, agent)

        assert node.id not in scheduler._running_nodes
        mock_set_status.assert_not_called()
        mock_timeout.assert_not_called()
        mock_comm.send_task_assignment.assert_not_called()

    @pytest.mark.asyncio
    async def test_assign_node_aborts_when_ready_transition_loses_race(
        self,
        scheduler: DAGScheduler,
    ):
        node = FakeNode(status=STATUS_READY, retry_count=0, agent_role="writer")
        agent = FakeAgent(role="writer")
        session = AsyncMock()
        lost_race_result = MagicMock()
        lost_race_result.rowcount = 0
        session.execute = AsyncMock(return_value=lost_race_result)

        with (
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock) as mock_set_status,
            patch("app.services.dag_scheduler.add_timeout_watch", new_callable=AsyncMock) as mock_timeout,
            patch("app.services.dag_scheduler.communicator") as mock_comm,
        ):
            mock_comm.send_task_assignment = AsyncMock()
            mock_comm.send_status_update = AsyncMock()

            await scheduler._assign_node(session, node, agent)

        assert node.id not in scheduler._running_nodes
        mock_set_status.assert_not_called()
        mock_timeout.assert_not_called()
        mock_comm.send_task_assignment.assert_not_called()

    @pytest.mark.asyncio
    async def test_assign_node_emits_routing_labels_in_events(
        self,
        scheduler: DAGScheduler,
    ):
        node = FakeNode(status=STATUS_READY, retry_count=0, agent_role="writer")
        agent = FakeAgent(role="writer")
        session = AsyncMock()
        session.expire_all = MagicMock()
        session.get = AsyncMock(
            side_effect=[
                FakeNode(
                    node_id=node.id,
                    status=STATUS_RUNNING,
                    assigned_agent=agent.id,
                    agent_role="writer",
                ),
                SimpleNamespace(checkpoint_data={"control": {"status": "active"}}),
            ]
        )
        update_result = MagicMock()
        update_result.rowcount = 1
        session.execute = AsyncMock(side_effect=[update_result, MagicMock()])

        with (
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock),
            patch("app.services.dag_scheduler.add_timeout_watch", new_callable=AsyncMock),
            patch("app.services.dag_scheduler.communicator") as mock_comm,
        ):
            mock_comm.send_task_assignment = AsyncMock()
            mock_comm.send_status_update = AsyncMock()

            assigned = await scheduler._assign_node(
                session,
                node,
                agent,
                routing_reason="capability_match",
                routing_mode="capability_first",
            )

        assert assigned is True
        assign_kwargs = mock_comm.send_task_assignment.await_args.kwargs
        assert assign_kwargs["payload"]["routing_reason"] == "capability_match"
        assert assign_kwargs["payload"]["routing_mode"] == "capability_first"
        status_kwargs = mock_comm.send_status_update.await_args.kwargs
        assert status_kwargs["extra"]["routing_reason"] == "capability_match"
        assert status_kwargs["extra"]["routing_mode"] == "capability_first"


# ---------------------------------------------------------------------------
# Test: on_node_completed
# ---------------------------------------------------------------------------


class TestOnNodeCompleted:
    @pytest.mark.asyncio
    async def test_node_completed_removes_from_running(self, scheduler: DAGScheduler):
        node_id = make_uuid()
        agent_id = make_uuid()
        scheduler._running_nodes[node_id] = agent_id
        fake_node = FakeNode(
            node_id=node_id,
            status=STATUS_RUNNING,
            assigned_agent=agent_id,
        )

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock),
            patch("app.services.dag_scheduler.remove_timeout_watch", new_callable=AsyncMock),
            patch.object(scheduler, "_activate_dependents", new_callable=AsyncMock),
        ):
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=fake_node)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler.on_node_completed(node_id, "result text", agent_id)

        assert node_id not in scheduler._running_nodes

    @pytest.mark.asyncio
    async def test_node_completed_triggers_schedule_event(self, scheduler: DAGScheduler):
        node_id = make_uuid()
        agent_id = make_uuid()
        scheduler._running_nodes[node_id] = agent_id
        fake_node = FakeNode(
            node_id=node_id,
            status=STATUS_RUNNING,
            assigned_agent=agent_id,
        )

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock),
            patch("app.services.dag_scheduler.remove_timeout_watch", new_callable=AsyncMock),
            patch.object(scheduler, "_activate_dependents", new_callable=AsyncMock),
        ):
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=fake_node)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler.on_node_completed(node_id, "result text", agent_id)

        assert scheduler._schedule_event.is_set()

    @pytest.mark.asyncio
    async def test_node_completed_delegates_fsm_progression_to_flow_controller(
        self, scheduler: DAGScheduler
    ):
        node_id = make_uuid()
        agent_id = make_uuid()
        scheduler._running_nodes[node_id] = agent_id
        scheduler._node_roles[node_id] = "writer"
        fake_node = FakeNode(
            node_id=node_id,
            status=STATUS_RUNNING,
            assigned_agent=agent_id,
            agent_role="writer",
        )

        scheduler._flow_controller.on_node_completed = AsyncMock(return_value=True)
        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock),
            patch("app.services.dag_scheduler.remove_timeout_watch", new_callable=AsyncMock),
            patch.object(scheduler, "_activate_dependents", new_callable=AsyncMock),
        ):
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=fake_node)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler.on_node_completed(node_id, "result text", agent_id)

        scheduler._flow_controller.on_node_completed.assert_awaited_once()
        kwargs = scheduler._flow_controller.on_node_completed.await_args.kwargs
        assert kwargs["task_id"] == scheduler.task_id
        assert kwargs["node_role"] == "writer"


# ---------------------------------------------------------------------------
# Test: on_node_failed
# ---------------------------------------------------------------------------


class TestOnNodeFailed:
    @pytest.mark.asyncio
    async def test_retries_under_max(self, scheduler: DAGScheduler):
        """失败次数 < MAX_RETRIES 时回到 ready 队列。"""
        node_id = make_uuid()
        agent_id = make_uuid()
        scheduler._running_nodes[node_id] = agent_id

        fake_node = FakeNode(
            node_id=node_id,
            status=STATUS_RUNNING,
            retry_count=0,
            assigned_agent=agent_id,
        )

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock),
            patch("app.services.dag_scheduler.remove_timeout_watch", new_callable=AsyncMock),
            patch("app.services.dag_scheduler.push_ready_node", new_callable=AsyncMock) as mock_push,
        ):
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=fake_node)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler.on_node_failed(node_id, "some error", agent_id)

        # 应该推入就绪队列
        mock_push.assert_called_once_with(str(node_id), priority=1.0)
        assert node_id not in scheduler._running_nodes

    @pytest.mark.asyncio
    async def test_permanently_fails_at_max_retries(self, scheduler: DAGScheduler):
        """达到 MAX_RETRIES 时节点标记为 failed。"""
        node_id = make_uuid()
        agent_id = make_uuid()
        scheduler._running_nodes[node_id] = agent_id

        fake_node = FakeNode(
            node_id=node_id,
            status=STATUS_RUNNING,
            retry_count=MAX_RETRIES - 1,
            assigned_agent=agent_id,
        )

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock) as mock_set_status,
            patch("app.services.dag_scheduler.remove_timeout_watch", new_callable=AsyncMock),
            patch("app.services.dag_scheduler.push_ready_node", new_callable=AsyncMock) as mock_push,
        ):
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=fake_node)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler.on_node_failed(node_id, "final error", agent_id)

        # 不应推入就绪队列
        mock_push.assert_not_called()
        # 应该设置为 failed
        mock_set_status.assert_called_with(
            scheduler.task_id, str(node_id), STATUS_FAILED
        )
        assert node_id not in scheduler._running_nodes

    @pytest.mark.asyncio
    async def test_missing_node_is_noop(self, scheduler: DAGScheduler):
        """节点不存在于DB时安全跳过。"""
        node_id = make_uuid()
        agent_id = make_uuid()

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
        ):
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=None)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            # 不应抛异常
            await scheduler.on_node_failed(node_id, "error", agent_id)


# ---------------------------------------------------------------------------
# Test: control cooperation (pause/resume + retry wake)
# ---------------------------------------------------------------------------


class TestControlCooperation:
    @pytest.mark.asyncio
    async def test_pause_requested_blocks_dispatch_without_interrupting_running(
        self,
        scheduler: DAGScheduler,
    ):
        running_node_id = make_uuid()
        scheduler._running_nodes[running_node_id] = make_uuid()
        scheduler._node_roles[running_node_id] = "writer"

        ready_node = FakeNode(status=STATUS_READY, agent_role="writer")
        task = SimpleNamespace(checkpoint_data={"control": {"status": "pause_requested"}})

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch.object(scheduler, "_match_agent", new_callable=AsyncMock) as mock_match,
            patch.object(scheduler, "_assign_node", new_callable=AsyncMock) as mock_assign,
        ):
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [ready_node]
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=task)
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            dispatched = await scheduler._dispatch_ready_nodes()

        assert dispatched == 0
        assert running_node_id in scheduler._running_nodes
        mock_match.assert_not_called()
        mock_assign.assert_not_called()

    @pytest.mark.asyncio
    async def test_pause_requested_promotes_to_paused_only_after_running_settles(
        self,
        scheduler: DAGScheduler,
    ):
        node_id = make_uuid()
        scheduler._running_nodes[node_id] = make_uuid()

        task = SimpleNamespace(checkpoint_data={"control": {"status": "pause_requested"}})

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.communicator") as mock_comm,
        ):
            mock_comm.send_task_event = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=task)
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler._dispatch_ready_nodes()
            assert task.checkpoint_data["control"]["status"] == "pause_requested"

            scheduler._running_nodes.clear()
            await scheduler._dispatch_ready_nodes()

        assert task.checkpoint_data["control"]["status"] == "paused"
        sent_types = [call.kwargs["msg_type"] for call in mock_comm.send_task_event.await_args_list]
        assert sent_types == ["dag_update", "log"]

    @pytest.mark.asyncio
    async def test_resume_allows_ready_nodes_to_dispatch_again(
        self,
        scheduler: DAGScheduler,
    ):
        ready_node = FakeNode(status=STATUS_READY, agent_role="writer")
        agent = FakeAgent(role="writer")
        task = SimpleNamespace(checkpoint_data={"control": {"status": "active"}})

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch.object(scheduler, "_match_agent", new_callable=AsyncMock) as mock_match,
            patch.object(scheduler, "_assign_node", new_callable=AsyncMock) as mock_assign,
        ):
            mock_match.return_value = agent
            mock_assign.return_value = True
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [ready_node]
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=task)
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            dispatched = await scheduler._dispatch_ready_nodes()

        assert dispatched == 1
        mock_match.assert_awaited_once()
        mock_assign.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retry_ready_node_reenters_dispatch_path_after_wake(
        self,
        scheduler: DAGScheduler,
    ):
        retried_ready_node = FakeNode(status=STATUS_READY, agent_role="writer")
        agent = FakeAgent(role="writer")
        task = SimpleNamespace(checkpoint_data={"control": {"status": "active"}})

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch.object(scheduler, "_match_agent", new_callable=AsyncMock) as mock_match,
            patch.object(scheduler, "_assign_node", new_callable=AsyncMock) as mock_assign,
        ):
            mock_match.return_value = agent
            mock_assign.return_value = True
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [retried_ready_node]
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=task)
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            assert scheduler._schedule_event.is_set() is False
            scheduler.wake()
            assert scheduler._schedule_event.is_set() is True
            scheduler._schedule_event.clear()

            dispatched = await scheduler._dispatch_ready_nodes()

        assert dispatched == 1
        mock_assign.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pause_requested_stops_further_assignments_between_ready_nodes(
        self,
        scheduler: DAGScheduler,
    ):
        first = FakeNode(status=STATUS_READY, retry_count=0, agent_role="writer")
        second = FakeNode(status=STATUS_READY, retry_count=1, agent_role="writer")
        agents = [FakeAgent(role="writer"), FakeAgent(role="writer")]
        task = SimpleNamespace(checkpoint_data={"control": {"status": "active"}})

        async def assign_then_pause(
            _session: object,
            node: FakeNode,
            _agent: FakeAgent,
            **_: object,
        ) -> bool:
            if node.id == first.id:
                task.checkpoint_data["control"]["status"] = "pause_requested"
                return True
            return True

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch.object(scheduler, "_match_agent", new=AsyncMock(side_effect=agents)),
            patch.object(scheduler, "_assign_node", new=AsyncMock(side_effect=assign_then_pause)) as mock_assign,
        ):
            pending_result = MagicMock()
            pending_result.scalars.return_value.all.return_value = []
            ready_result = MagicMock()
            ready_result.scalars.return_value.all.return_value = [first, second]
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=task)
            mock_session.execute = AsyncMock(side_effect=[pending_result, ready_result])
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            dispatched = await scheduler._dispatch_ready_nodes()

        assert dispatched == 1
        assert [call.args[1] for call in mock_assign.await_args_list] == [first]


# ---------------------------------------------------------------------------
# Test: stale callback guard for skipped running nodes
# ---------------------------------------------------------------------------


class TestSkippedRunningNodeCallbacks:
    @pytest.mark.asyncio
    async def test_stale_completion_callback_is_ignored_for_skipped_running_node(
        self,
        scheduler: DAGScheduler,
    ):
        node_id = make_uuid()
        agent_id = make_uuid()

        skipped_node = FakeNode(node_id=node_id, status="skipped")

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock) as mock_set_status,
            patch("app.services.dag_scheduler.remove_timeout_watch", new_callable=AsyncMock) as mock_remove_watch,
            patch.object(scheduler, "_activate_dependents", new_callable=AsyncMock) as mock_activate,
        ):
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=skipped_node)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler.on_node_completed(node_id, "late result", agent_id)

        assert node_id not in scheduler._running_nodes
        assert node_id not in scheduler._node_roles
        mock_set_status.assert_not_called()
        mock_activate.assert_not_called()
        assert mock_remove_watch.await_count == 2

    @pytest.mark.asyncio
    async def test_stale_failure_callback_is_ignored_for_skipped_running_node(
        self,
        scheduler: DAGScheduler,
    ):
        node_id = make_uuid()
        agent_id = make_uuid()

        skipped_node = FakeNode(node_id=node_id, status="skipped", retry_count=0)

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock) as mock_set_status,
            patch("app.services.dag_scheduler.push_ready_node", new_callable=AsyncMock) as mock_push_ready,
            patch("app.services.dag_scheduler.remove_timeout_watch", new_callable=AsyncMock) as mock_remove_watch,
        ):
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=skipped_node)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler.on_node_failed(node_id, "late error", agent_id)

        assert node_id not in scheduler._running_nodes
        assert node_id not in scheduler._node_roles
        mock_set_status.assert_not_called()
        mock_push_ready.assert_not_called()
        assert mock_remove_watch.await_count == 2

    @pytest.mark.asyncio
    async def test_late_completion_callback_is_ignored_after_requeue(
        self,
        scheduler: DAGScheduler,
    ):
        node_id = make_uuid()
        agent_id = make_uuid()
        requeued_node = FakeNode(
            node_id=node_id,
            status=STATUS_READY,
            retry_count=1,
            assigned_agent=None,
        )

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock) as mock_set_status,
            patch("app.services.dag_scheduler.remove_timeout_watch", new_callable=AsyncMock) as mock_remove_watch,
            patch.object(scheduler, "_activate_dependents", new_callable=AsyncMock) as mock_activate,
        ):
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=requeued_node)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler.on_node_completed(node_id, "late result", agent_id)

        mock_set_status.assert_not_called()
        mock_remove_watch.assert_not_called()
        mock_activate.assert_not_called()

    @pytest.mark.asyncio
    async def test_late_failure_callback_is_ignored_after_requeue(
        self,
        scheduler: DAGScheduler,
    ):
        node_id = make_uuid()
        agent_id = make_uuid()
        requeued_node = FakeNode(
            node_id=node_id,
            status=STATUS_READY,
            retry_count=1,
            assigned_agent=None,
        )

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock) as mock_set_status,
            patch("app.services.dag_scheduler.push_ready_node", new_callable=AsyncMock) as mock_push_ready,
            patch("app.services.dag_scheduler.remove_timeout_watch", new_callable=AsyncMock) as mock_remove_watch,
        ):
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=requeued_node)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler.on_node_failed(node_id, "late error", agent_id)

        mock_set_status.assert_not_called()
        mock_push_ready.assert_not_called()
        mock_remove_watch.assert_not_called()


# ---------------------------------------------------------------------------
# Test: run-loop pause semantics
# ---------------------------------------------------------------------------


class TestRunPauseSemantics:
    @pytest.mark.asyncio
    async def test_run_does_not_fail_deadlock_when_paused_and_no_running_nodes(
        self,
        scheduler: DAGScheduler,
    ):
        task = SimpleNamespace(checkpoint_data={"control": {"status": "paused"}})

        async def _stop_after_timeout_check() -> None:
            scheduler.stop()

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch.object(scheduler, "_init_ready_nodes", new_callable=AsyncMock),
            patch.object(
                scheduler,
                "_check_timeouts",
                new=AsyncMock(side_effect=_stop_after_timeout_check),
            ),
            patch.object(scheduler, "_all_nodes_terminal", new=AsyncMock(return_value=False)),
            patch.object(scheduler, "_has_undone_nodes", new=AsyncMock(return_value=True)),
            patch.object(scheduler, "_mark_task_failed", new_callable=AsyncMock) as mock_failed,
        ):
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=task)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler.run()

        mock_failed.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_pause_requested_without_running_stays_cooperative(
        self,
        scheduler: DAGScheduler,
    ):
        task = SimpleNamespace(checkpoint_data={"control": {"status": "pause_requested"}})

        async def _stop_after_timeout_check() -> None:
            scheduler.stop()

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch.object(scheduler, "_init_ready_nodes", new_callable=AsyncMock),
            patch.object(
                scheduler,
                "_check_timeouts",
                new=AsyncMock(side_effect=_stop_after_timeout_check),
            ),
            patch.object(scheduler, "_all_nodes_terminal", new=AsyncMock(return_value=False)),
            patch.object(scheduler, "_has_undone_nodes", new=AsyncMock(return_value=True)),
            patch.object(scheduler, "_mark_task_failed", new_callable=AsyncMock) as mock_failed,
        ):
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=task)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler.run()

        assert task.checkpoint_data["control"]["status"] == "paused"
        mock_failed.assert_not_called()


class TestRunTerminalSemantics:
    @pytest.mark.asyncio
    async def test_run_marks_task_failed_when_all_nodes_terminal_but_failed_present(
        self,
        scheduler: DAGScheduler,
    ):
        with (
            patch.object(scheduler, "_init_ready_nodes", new_callable=AsyncMock),
            patch.object(scheduler, "_check_timeouts", new_callable=AsyncMock),
            patch.object(scheduler, "_dispatch_ready_nodes", new=AsyncMock(return_value=0)),
            patch.object(scheduler, "_all_nodes_terminal", new=AsyncMock(return_value=True)),
            patch.object(scheduler, "_has_failed_nodes", new=AsyncMock(return_value=True)),
            patch.object(scheduler, "_mark_task_done", new_callable=AsyncMock) as mock_done,
            patch.object(scheduler, "_mark_task_failed", new_callable=AsyncMock) as mock_failed,
        ):
            await scheduler.run()

        mock_done.assert_not_called()
        mock_failed.assert_awaited_once()
        assert "DAG completed with failed nodes" in mock_failed.await_args.args[0]


class TestSkipSemantics:
    @pytest.mark.asyncio
    async def test_activate_dependents_treats_skipped_dependency_as_satisfied(
        self,
        scheduler: DAGScheduler,
    ):
        skipped_node_id = make_uuid()
        dependent = FakeNode(
            status=STATUS_PENDING,
            depends_on=[skipped_node_id],
        )

        pending_result = MagicMock()
        pending_result.scalars.return_value.all.return_value = [dependent]
        satisfied_result = MagicMock()
        satisfied_result.all.return_value = [(skipped_node_id,)]
        activate_result = MagicMock()
        activate_result.rowcount = 1

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock) as mock_set_status,
            patch("app.services.dag_scheduler.push_ready_node", new_callable=AsyncMock) as mock_push_ready,
        ):
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(
                side_effect=[pending_result, satisfied_result, activate_result]
            )
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler._activate_dependents(skipped_node_id)

        mock_set_status.assert_awaited_once_with(
            scheduler.task_id,
            str(dependent.id),
            STATUS_READY,
        )
        mock_push_ready.assert_awaited_once_with(str(dependent.id), priority=0.0)

    @pytest.mark.asyncio
    async def test_activate_dependents_does_not_resurrect_node_that_left_pending(
        self,
        scheduler: DAGScheduler,
    ):
        skipped_node_id = make_uuid()
        dependent = FakeNode(
            status=STATUS_PENDING,
            depends_on=[skipped_node_id],
        )

        pending_result = MagicMock()
        pending_result.scalars.return_value.all.return_value = [dependent]
        satisfied_result = MagicMock()
        satisfied_result.all.return_value = [(skipped_node_id,)]
        lost_race_result = MagicMock()
        lost_race_result.rowcount = 0

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock) as mock_set_status,
            patch("app.services.dag_scheduler.push_ready_node", new_callable=AsyncMock) as mock_push_ready,
        ):
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(
                side_effect=[pending_result, satisfied_result, lost_race_result]
            )
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler._activate_dependents(skipped_node_id)

        mock_set_status.assert_not_called()
        mock_push_ready.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_prefers_fresh_ready_node_over_retried_node(
        self,
        scheduler: DAGScheduler,
    ):
        retried = FakeNode(status=STATUS_READY, retry_count=2, agent_role="writer")
        fresh = FakeNode(status=STATUS_READY, retry_count=0, agent_role="writer")
        task = SimpleNamespace(checkpoint_data={"control": {"status": "active"}})
        agents = [FakeAgent(role="writer"), FakeAgent(role="writer")]

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch.object(scheduler, "_match_agent", new=AsyncMock(side_effect=agents)),
            patch.object(scheduler, "_assign_node", new_callable=AsyncMock) as mock_assign,
        ):
            mock_assign.return_value = True
            pending_result = MagicMock()
            pending_result.scalars.return_value.all.return_value = []
            ready_result = MagicMock()
            ready_result.scalars.return_value.all.return_value = [retried, fresh]
            mock_session = AsyncMock()
            mock_session.get = AsyncMock(return_value=task)
            mock_session.execute = AsyncMock(side_effect=[pending_result, ready_result])
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            dispatched = await scheduler._dispatch_ready_nodes()

        assert dispatched == 2
        assigned_nodes = [call.args[1] for call in mock_assign.await_args_list]
        assert assigned_nodes == [fresh, retried]


# ---------------------------------------------------------------------------
# Test: _check_timeouts
# ---------------------------------------------------------------------------


class TestCheckTimeouts:
    @pytest.mark.asyncio
    async def test_no_timeouts_is_noop(self, scheduler: DAGScheduler):
        with patch(
            "app.services.dag_scheduler.get_timed_out_nodes",
            new_callable=AsyncMock,
            return_value=[],
        ):
            # 不应抛异常
            await scheduler._check_timeouts()

    @pytest.mark.asyncio
    async def test_timeout_triggers_failure(self, scheduler: DAGScheduler):
        node_id = make_uuid()
        agent_id = make_uuid()
        scheduler._running_nodes[node_id] = agent_id

        with (
            patch(
                "app.services.dag_scheduler.get_timed_out_nodes",
                new_callable=AsyncMock,
                return_value=[str(node_id)],
            ),
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch.object(
                scheduler, "on_node_failed", new_callable=AsyncMock
            ) as mock_fail,
        ):
            stale_result = MagicMock()
            stale_result.all.return_value = []
            mock_session = AsyncMock()
            mock_session.execute = AsyncMock(return_value=stale_result)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            await scheduler._check_timeouts()

        mock_fail.assert_called_once_with(
            node_id=node_id,
            error="Execution timeout",
            agent_id=agent_id,
        )

    @pytest.mark.asyncio
    async def test_timeout_unknown_node_cleaned_up(self, scheduler: DAGScheduler):
        """当前 task 的过期 watch 如已脱离运行态，应被清理。"""
        node_id_str = str(make_uuid())
        watch_member = f"{scheduler.task_id}:{node_id_str}"

        with (
            patch(
                "app.services.dag_scheduler.get_timed_out_nodes",
                new_callable=AsyncMock,
                return_value=[watch_member],
            ),
            patch(
                "app.services.dag_scheduler.remove_timeout_watch",
                new_callable=AsyncMock,
            ) as mock_remove,
        ):
            await scheduler._check_timeouts()

        assert mock_remove.await_args_list[0].args == (watch_member,)
        assert mock_remove.await_args_list[1].args == (node_id_str,)

    @pytest.mark.asyncio
    async def test_timeout_watch_for_other_task_is_not_removed(self, scheduler: DAGScheduler):
        foreign_watch = f"{make_uuid()}:{make_uuid()}"

        with (
            patch(
                "app.services.dag_scheduler.get_timed_out_nodes",
                new_callable=AsyncMock,
                return_value=[foreign_watch],
            ),
            patch(
                "app.services.dag_scheduler.remove_timeout_watch",
                new_callable=AsyncMock,
            ) as mock_remove,
            patch.object(
                scheduler, "on_node_failed", new_callable=AsyncMock
            ) as mock_fail,
        ):
            await scheduler._check_timeouts()

        mock_remove.assert_not_called()
        mock_fail.assert_not_called()


class TestAssignNodeRecovery:
    @pytest.mark.asyncio
    async def test_assign_node_reverts_when_post_commit_side_effect_fails(
        self,
        scheduler: DAGScheduler,
    ):
        node = FakeNode(status=STATUS_READY, retry_count=0, agent_role="writer")
        agent = FakeAgent(role="writer")
        session = AsyncMock()
        session.expire_all = MagicMock()
        session.get = AsyncMock(
            side_effect=[
                FakeNode(
                    node_id=node.id,
                    status=STATUS_RUNNING,
                    assigned_agent=agent.id,
                    agent_role="writer",
                ),
                SimpleNamespace(checkpoint_data={"control": {"status": "active"}}),
            ]
        )

        update_result = MagicMock()
        update_result.rowcount = 1
        session.execute = AsyncMock(side_effect=[update_result, MagicMock()])

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock) as mock_set_status,
            patch("app.services.dag_scheduler.add_timeout_watch", new_callable=AsyncMock),
            patch("app.services.dag_scheduler.remove_timeout_watch", new_callable=AsyncMock),
            patch("app.services.dag_scheduler.push_ready_node", new_callable=AsyncMock) as mock_push_ready,
            patch("app.services.dag_scheduler.communicator") as mock_comm,
        ):
            compensation_session = AsyncMock()
            compensation_result = MagicMock()
            compensation_result.rowcount = 1
            compensation_session.execute = AsyncMock(
                side_effect=[compensation_result, MagicMock()]
            )
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=compensation_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_comm.send_task_assignment = AsyncMock(side_effect=RuntimeError("boom"))
            mock_comm.send_status_update = AsyncMock()

            assigned = await scheduler._assign_node(session, node, agent)

        assert assigned is False
        assert node.id not in scheduler._running_nodes
        assert node.id not in scheduler._node_roles
        assert mock_set_status.await_args_list[0].args == (
            scheduler.task_id,
            str(node.id),
            STATUS_RUNNING,
        )
        assert mock_set_status.await_args_list[1].args == (
            scheduler.task_id,
            str(node.id),
            STATUS_READY,
        )
        mock_push_ready.assert_awaited_once_with(str(node.id), priority=0.0)

    @pytest.mark.asyncio
    async def test_assign_node_keeps_running_when_status_update_fails_after_delivery(
        self,
        scheduler: DAGScheduler,
    ):
        node = FakeNode(status=STATUS_READY, retry_count=0, agent_role="writer")
        agent = FakeAgent(role="writer")
        session = AsyncMock()
        session.expire_all = MagicMock()
        session.get = AsyncMock(
            side_effect=[
                FakeNode(
                    node_id=node.id,
                    status=STATUS_RUNNING,
                    assigned_agent=agent.id,
                    agent_role="writer",
                ),
                SimpleNamespace(checkpoint_data={"control": {"status": "active"}}),
            ]
        )

        update_result = MagicMock()
        update_result.rowcount = 1
        session.execute = AsyncMock(side_effect=[update_result, MagicMock()])

        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock) as mock_set_status,
            patch("app.services.dag_scheduler.add_timeout_watch", new_callable=AsyncMock),
            patch("app.services.dag_scheduler.remove_timeout_watch", new_callable=AsyncMock) as mock_remove_watch,
            patch("app.services.dag_scheduler.push_ready_node", new_callable=AsyncMock) as mock_push_ready,
            patch("app.services.dag_scheduler.communicator") as mock_comm,
        ):
            mock_factory.return_value.__aenter__ = AsyncMock()
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_comm.send_task_assignment = AsyncMock()
            mock_comm.send_status_update = AsyncMock(side_effect=RuntimeError("status boom"))

            assigned = await scheduler._assign_node(session, node, agent)

        assert assigned is True
        assert scheduler._running_nodes[node.id] == agent.id
        assert scheduler._node_roles[node.id] == "writer"
        assert mock_set_status.await_count == 1
        mock_remove_watch.assert_not_called()
        mock_push_ready.assert_not_called()


# ---------------------------------------------------------------------------
# Test: Scheduler Registry
# ---------------------------------------------------------------------------


class TestSchedulerRegistry:
    def test_get_scheduler_returns_none_when_not_started(self):
        assert get_scheduler(make_uuid()) is None

    def test_stop_scheduler_noop_when_not_exists(self):
        # 不应抛异常
        stop_scheduler(make_uuid())

    @pytest.mark.asyncio
    async def test_start_scheduler_registers(self):
        task_id = make_uuid()

        with (
            patch.object(DAGScheduler, "run", new_callable=AsyncMock),
        ):
            scheduler = await start_scheduler(task_id)
            assert get_scheduler(task_id) is scheduler

        # 清理
        _active_schedulers.pop(task_id, None)

    @pytest.mark.asyncio
    async def test_start_scheduler_returns_existing(self):
        task_id = make_uuid()
        existing = DAGScheduler(task_id)
        _active_schedulers[task_id] = existing

        result = await start_scheduler(task_id)
        assert result is existing

        # 清理
        _active_schedulers.pop(task_id, None)


# ---------------------------------------------------------------------------
# Test: _is_dag_complete / _has_undone_nodes
# ---------------------------------------------------------------------------


class TestDagCompletion:
    @pytest.mark.asyncio
    async def test_is_complete_when_all_done(self, scheduler: DAGScheduler):
        with patch("app.services.dag_scheduler.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = None  # 没有未完成节点
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            assert await scheduler._is_dag_complete() is True

    @pytest.mark.asyncio
    async def test_is_not_complete_with_pending(self, scheduler: DAGScheduler):
        with patch("app.services.dag_scheduler.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = FakeNode()  # 有未完成节点
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            assert await scheduler._is_dag_complete() is False


# ---------------------------------------------------------------------------
# Test: _mark_task_done / _mark_task_failed
# ---------------------------------------------------------------------------


class TestMarkTask:
    @pytest.mark.asyncio
    async def test_mark_task_done(self, scheduler: DAGScheduler):
        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.communicator") as mock_comm,
            patch("app.services.long_text_fsm.LongTextFSM.finalize_output", new_callable=AsyncMock) as mock_finalize,
        ):
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_comm.send_status_update = AsyncMock()
            mock_comm.send_task_event = AsyncMock()

            await scheduler._mark_task_done()

        assert mock_session.execute.call_count >= 1
        mock_session.commit.assert_called_once()
        mock_finalize.assert_awaited_once()
        mock_comm.send_status_update.assert_called_once()
        mock_comm.send_task_event.assert_called_once()
        assert mock_comm.send_task_event.await_args.kwargs["msg_type"] == "task_done"
        assert mock_comm.send_task_event.await_args.kwargs["payload"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_mark_task_done_ignores_notification_failures(self, scheduler: DAGScheduler):
        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.communicator") as mock_comm,
            patch("app.services.long_text_fsm.LongTextFSM.finalize_output", new_callable=AsyncMock),
        ):
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_comm.send_status_update = AsyncMock(side_effect=RuntimeError("boom"))
            mock_comm.send_task_event = AsyncMock()

            await scheduler._mark_task_done()

        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_task_failed(self, scheduler: DAGScheduler):
        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.communicator") as mock_comm,
        ):
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_comm.send_status_update = AsyncMock()
            mock_comm.send_task_event = AsyncMock()

            await scheduler._mark_task_failed("test error")

        mock_session.execute.assert_called_once()
        mock_comm.send_status_update.assert_called_once()
        mock_comm.send_task_event.assert_called_once()
        assert mock_comm.send_task_event.await_args.kwargs["payload"]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_mark_task_failed_ignores_notification_failures(self, scheduler: DAGScheduler):
        with (
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch("app.services.dag_scheduler.communicator") as mock_comm,
        ):
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_comm.send_status_update = AsyncMock(side_effect=RuntimeError("boom"))
            mock_comm.send_task_event = AsyncMock()

            await scheduler._mark_task_failed("test error")

        mock_session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Test: consistency repair-target injection path
# ---------------------------------------------------------------------------


class TestConsistencyRepairWave:
    @pytest.mark.asyncio
    async def test_drain_task_results_injects_repair_wave_on_consistency_fail(
        self,
        scheduler: DAGScheduler,
    ):
        node_id = make_uuid()
        agent_id = make_uuid()
        payload = {
            "status": "done",
            "output": json.dumps(
                {
                    "pass": False,
                    "style_conflicts": [],
                    "claim_conflicts": [],
                    "repair_targets": [1, 3],
                },
                ensure_ascii=False,
            ),
        }
        envelope = SimpleNamespace(
            msg_type="task_result",
            node_id=str(node_id),
            from_agent=str(agent_id),
            payload=payload,
        )

        with (
            patch(
                "app.services.dag_scheduler.xread_latest",
                new_callable=AsyncMock,
                return_value=[SimpleNamespace(message_id="1-0", data={})],
            ),
            patch(
                "app.services.dag_scheduler.MessageEnvelope.from_redis",
                return_value=envelope,
            ),
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch.object(
                scheduler,
                "_inject_consistency_repair_wave",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_inject,
            patch.object(
                scheduler,
                "on_node_completed",
                new_callable=AsyncMock,
            ) as mock_completed,
            patch.object(
                scheduler,
                "on_node_failed",
                new_callable=AsyncMock,
            ) as mock_failed,
        ):
            mock_session = AsyncMock()
            role_row = MagicMock()
            role_row.first.return_value = ("consistency", "一致性检查", 0)
            mock_session.execute = AsyncMock(return_value=role_row)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler._drain_task_results()

        mock_inject.assert_not_awaited()
        mock_completed.assert_awaited_once()
        completed_kwargs = mock_completed.await_args.kwargs
        assert completed_kwargs["node_id"] == node_id
        assert completed_kwargs["agent_id"] == agent_id
        completed_output = str(completed_kwargs.get("result") or "")
        assert _is_invalid_output_for_role("consistency", completed_output) is False
        parsed_completed = json.loads(completed_output)
        assert parsed_completed.get("pass") is False
        mock_failed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_drain_task_results_softens_when_consistency_budget_exhausted(
        self,
        scheduler: DAGScheduler,
    ):
        node_id = make_uuid()
        agent_id = make_uuid()
        payload = {
            "status": "done",
            "output": json.dumps(
                {
                    "pass": False,
                    "style_conflicts": [{"chapter_index": 2, "severity": "high"}],
                    "claim_conflicts": [{"chapter_index": 2, "severity": "high"}],
                    "repair_targets": [2],
                    "repair_priority": [2],
                    "severity_summary": {"critical": 0, "high": 1, "medium": 0, "low": 0},
                },
                ensure_ascii=False,
            ),
        }
        envelope = SimpleNamespace(
            msg_type="task_result",
            node_id=str(node_id),
            from_agent=str(agent_id),
            payload=payload,
        )

        with (
            patch(
                "app.services.dag_scheduler.xread_latest",
                new_callable=AsyncMock,
                return_value=[SimpleNamespace(message_id="1-0", data={})],
            ),
            patch(
                "app.services.dag_scheduler.MessageEnvelope.from_redis",
                return_value=envelope,
            ),
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch.object(
                scheduler,
                "_inject_consistency_repair_wave",
                new_callable=AsyncMock,
                return_value=False,
            ) as mock_inject,
            patch.object(
                scheduler,
                "_consume_consistency_repair_budget",
                new_callable=AsyncMock,
                return_value=(
                    False,
                    [2],
                    {
                        "total_points": 4,
                        "remaining_points_before": 1,
                        "required_points": 5,
                        "selected_targets": [2],
                    },
                ),
            ) as mock_budget,
            patch.object(
                scheduler,
                "_should_soften_consistency_failure",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_soften,
            patch.object(
                scheduler,
                "_record_consistency_soft_failure",
                new_callable=AsyncMock,
            ) as mock_record_soft,
            patch.object(
                scheduler,
                "on_node_completed",
                new_callable=AsyncMock,
            ) as mock_completed,
            patch.object(
                scheduler,
                "on_node_failed",
                new_callable=AsyncMock,
            ) as mock_failed,
        ):
            mock_session = AsyncMock()
            role_row = MagicMock()
            role_row.first.return_value = ("consistency", "一致性检查", MAX_RETRIES - 1)
            mock_session.execute = AsyncMock(return_value=role_row)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler._drain_task_results()

        mock_inject.assert_not_awaited()
        mock_budget.assert_awaited_once()
        mock_soften.assert_awaited_once()
        mock_record_soft.assert_awaited_once()
        mock_completed.assert_awaited_once()
        mock_failed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_drain_task_results_budget_exhausted_before_max_retries_keeps_retrying(
        self,
        scheduler: DAGScheduler,
    ):
        node_id = make_uuid()
        agent_id = make_uuid()
        payload = {
            "status": "done",
            "output": json.dumps(
                {
                    "pass": False,
                    "style_conflicts": [{"chapter_index": 2, "severity": "high"}],
                    "claim_conflicts": [{"chapter_index": 2, "severity": "high"}],
                    "repair_targets": [2],
                    "repair_priority": [2],
                    "severity_summary": {"critical": 0, "high": 1, "medium": 0, "low": 0},
                },
                ensure_ascii=False,
            ),
        }
        envelope = SimpleNamespace(
            msg_type="task_result",
            node_id=str(node_id),
            from_agent=str(agent_id),
            payload=payload,
        )

        with (
            patch(
                "app.services.dag_scheduler.xread_latest",
                new_callable=AsyncMock,
                return_value=[SimpleNamespace(message_id="1-0", data={})],
            ),
            patch(
                "app.services.dag_scheduler.MessageEnvelope.from_redis",
                return_value=envelope,
            ),
            patch("app.services.dag_scheduler.async_session_factory") as mock_factory,
            patch.object(
                scheduler,
                "_inject_consistency_repair_wave",
                new_callable=AsyncMock,
                return_value=False,
            ) as mock_inject,
            patch.object(
                scheduler,
                "_consume_consistency_repair_budget",
                new_callable=AsyncMock,
                return_value=(
                    False,
                    [2],
                    {
                        "total_points": 4,
                        "remaining_points_before": 1,
                        "required_points": 5,
                        "selected_targets": [2],
                    },
                ),
            ) as mock_budget,
            patch.object(
                scheduler,
                "_record_consistency_soft_failure",
                new_callable=AsyncMock,
            ) as mock_record_soft,
            patch.object(
                scheduler,
                "on_node_completed",
                new_callable=AsyncMock,
            ) as mock_completed,
            patch.object(
                scheduler,
                "on_node_failed",
                new_callable=AsyncMock,
            ) as mock_failed,
        ):
            mock_session = AsyncMock()
            role_row = MagicMock()
            role_row.first.return_value = ("consistency", "一致性检查", 0)
            mock_session.execute = AsyncMock(return_value=role_row)
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await scheduler._drain_task_results()

        mock_inject.assert_not_awaited()
        mock_budget.assert_awaited_once()
        mock_record_soft.assert_not_awaited()
        mock_completed.assert_not_awaited()
        mock_failed.assert_awaited_once()
        assert "budget exhausted before max retries" in str(mock_failed.await_args.kwargs.get("error", "")).lower()

    @pytest.mark.asyncio
    async def test_inject_repair_wave_compacts_nodes_for_quick_low_word_task(
        self,
        scheduler: DAGScheduler,
    ):
        added_nodes: list[object] = []
        mock_session = AsyncMock()

        writer_rows = MagicMock()
        writer_rows.all.return_value = []
        mock_session.execute = AsyncMock(return_value=writer_rows)
        mock_session.get = AsyncMock(
            return_value=SimpleNamespace(depth="quick", target_words=1200)
        )
        mock_session.add = MagicMock(side_effect=lambda node: added_nodes.append(node))
        mock_session.commit = AsyncMock()

        with (
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock),
            patch("app.services.dag_scheduler.push_ready_node", new_callable=AsyncMock),
        ):
            ok = await scheduler._inject_consistency_repair_wave(
                session=mock_session,
                repair_targets=[1, 2, 3],
            )

        assert ok is True
        roles = [getattr(node, "agent_role", "") for node in added_nodes]
        assert roles.count("writer") == 1
        assert roles.count("reviewer") == 0
        assert roles.count("consistency") == 1
        consistency = next(node for node in added_nodes if getattr(node, "agent_role", "") == "consistency")
        assert len(getattr(consistency, "depends_on", []) or []) == 1

    @pytest.mark.asyncio
    async def test_inject_repair_wave_keeps_reviewer_chain_for_standard_depth(
        self,
        scheduler: DAGScheduler,
    ):
        added_nodes: list[object] = []
        mock_session = AsyncMock()

        writer_rows = MagicMock()
        writer_rows.all.return_value = []
        mock_session.execute = AsyncMock(return_value=writer_rows)
        mock_session.get = AsyncMock(
            return_value=SimpleNamespace(depth="standard", target_words=4000)
        )
        mock_session.add = MagicMock(side_effect=lambda node: added_nodes.append(node))
        mock_session.commit = AsyncMock()

        with (
            patch("app.services.dag_scheduler.set_dag_node_status", new_callable=AsyncMock),
            patch("app.services.dag_scheduler.push_ready_node", new_callable=AsyncMock),
        ):
            ok = await scheduler._inject_consistency_repair_wave(
                session=mock_session,
                repair_targets=[1, 2],
            )

        assert ok is True
        roles = [getattr(node, "agent_role", "") for node in added_nodes]
        assert roles.count("writer") == 2
        assert roles.count("reviewer") == 2
        assert roles.count("consistency") == 1


# ---------------------------------------------------------------------------
# Test: _match_agent
# ---------------------------------------------------------------------------


class TestMatchAgent:
    @pytest.mark.asyncio
    async def test_returns_idle_agent_with_matching_role(self):
        agent = FakeAgent(role="writer")
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [agent]
        mock_session.execute = AsyncMock(return_value=mock_result)

        scheduler = DAGScheduler(make_uuid())
        matched, reason = await scheduler._match_agent(mock_session, "writer")
        assert matched is agent
        assert reason == "role_fallback"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_agent_available(self):
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        scheduler = DAGScheduler(make_uuid())
        matched, reason = await scheduler._match_agent(mock_session, "writer")
        assert matched is None
        assert reason == "no_idle_agent"


class TestOutputSanitization:
    def test_detects_waf_html_payload(self):
        assert _is_suspicious_node_output(
            '<!doctypehtml><meta name="aliyun_waf_aa" content="x">'
        )

    def test_allows_normal_markdown_payload(self):
        assert not _is_suspicious_node_output("# 标题\n\n正常内容。")
