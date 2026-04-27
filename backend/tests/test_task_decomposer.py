"""Tests for task_decomposer."""

from __future__ import annotations

import pytest

from app.schemas.task import DAGNodeSchema, DAGSchema, VALID_DEPTHS, VALID_MODES
from app.services.task_decomposer import (
    CyclicDAGError,
    TaskValidationError,
    decompose_task,
    parse_dag_response,
    validate_dag_acyclic,
    validate_task_input,
)
from tests.conftest import MockLLMClient


class TestValidateTaskInput:
    def test_valid_input(self):
        result = validate_task_input(
            "quantum computing report request", "report", "standard"
        )
        assert result.ok is True
        assert result.issues == []

    def test_invalid_fields(self):
        result = validate_task_input("bad", "invalid_mode", "invalid_depth")
        assert result.ok is False
        assert len(result.issues) >= 2

    def test_all_valid_modes(self):
        for mode in VALID_MODES:
            result = validate_task_input("long enough title", mode, "standard")
            assert result.ok is True

    def test_all_valid_depths(self):
        for depth in VALID_DEPTHS:
            result = validate_task_input("long enough title", "report", depth)
            assert result.ok is True


class TestValidateDAGAcyclic:
    def test_valid_dag(self):
        dag = DAGSchema(
            nodes=[
                DAGNodeSchema(id="n1", title="outline", role="outline", depends_on=[]),
                DAGNodeSchema(
                    id="n2", title="write", role="writer", depends_on=["n1"]
                ),
            ]
        )
        validate_dag_acyclic(dag)

    def test_cycle_raises(self):
        dag = DAGSchema(
            nodes=[
                DAGNodeSchema(id="n1", title="a", role="outline", depends_on=["n2"]),
                DAGNodeSchema(id="n2", title="b", role="writer", depends_on=["n1"]),
            ]
        )
        with pytest.raises(CyclicDAGError):
            validate_dag_acyclic(dag)

    def test_unknown_dependency_raises(self):
        dag = DAGSchema(
            nodes=[
                DAGNodeSchema(
                    id="n1", title="outline", role="outline", depends_on=["missing"]
                ),
            ]
        )
        with pytest.raises(CyclicDAGError, match="unknown"):
            validate_dag_acyclic(dag)


class TestParseDAGResponse:
    def test_valid_response(self):
        dag = parse_dag_response(
            {
                "nodes": [
                    {"id": "n1", "title": "outline", "role": "outline", "depends_on": []},
                    {"id": "n2", "title": "write", "role": "writer", "depends_on": ["n1"]},
                ]
            }
        )
        assert len(dag.nodes) == 2

    def test_duplicate_ids_raises(self):
        with pytest.raises(ValueError, match="[Dd]uplicate"):
            parse_dag_response(
                {
                    "nodes": [
                        {"id": "n1", "title": "a", "role": "outline", "depends_on": []},
                        {"id": "n1", "title": "b", "role": "writer", "depends_on": []},
                    ]
                }
            )

    def test_first_node_must_be_outline(self):
        with pytest.raises(ValueError, match="[Oo]utline"):
            parse_dag_response(
                {
                    "nodes": [
                        {"id": "n1", "title": "write", "role": "writer", "depends_on": []},
                    ]
                }
            )

    def test_role_is_optional_for_capability_only_nodes(self):
        dag = parse_dag_response(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "title": "research context",
                        "depends_on": [],
                        "required_capabilities": ["research"],
                    },
                    {
                        "id": "n2",
                        "title": "draft content",
                        "depends_on": ["n1"],
                        "required_capabilities": ["draft"],
                    },
                ]
            }
        )
        assert dag.nodes[0].role is None
        assert dag.nodes[1].role is None

    def test_routing_fields_are_accepted_and_normalized(self):
        dag = parse_dag_response(
            {
                "nodes": [
                    {
                        "id": "n1",
                        "title": "outline",
                        "role": "outline",
                        "depends_on": [],
                        "required_capabilities": [" PLAN ", "plan", ""],
                        "preferred_agents": [" writer-1 ", "writer-1"],
                        "routing_mode": "capability_first",
                    },
                ]
            }
        )
        assert dag.nodes[0].required_capabilities == ["PLAN"]
        assert dag.nodes[0].preferred_agents == ["writer-1"]
        assert dag.nodes[0].routing_mode == "capability_first"

    @pytest.mark.asyncio
    async def test_decompose_inserts_research_gate_when_missing(self):
        class _NoResearchLLM(MockLLMClient):
            async def chat_json(self, *args, **kwargs):  # noqa: ANN002, ANN003
                return {
                    "nodes": [
                        {"id": "n1", "title": "outline", "role": "outline", "depends_on": []},
                        {"id": "n2", "title": "write", "role": "writer", "depends_on": ["n1"]},
                        {"id": "n3", "title": "review", "role": "reviewer", "depends_on": ["n2"]},
                    ]
                }

        dag = await decompose_task(
            title="quantum computing technical report with full analysis",
            mode="report",
            depth="standard",
            target_words=10000,
            llm_client=_NoResearchLLM(),
        )

        roles = [node.role for node in dag.nodes]
        assert roles[0] == "outline"
        assert "researcher" in roles
        research_ids = [node.id for node in dag.nodes if node.role == "researcher"]
        writer_nodes = [node for node in dag.nodes if node.role == "writer"]
        assert writer_nodes
        assert all(any(rid in node.depends_on for rid in research_ids) for node in writer_nodes)

    @pytest.mark.asyncio
    async def test_decompose_injects_expansion_chain_for_long_target(self):
        class _ChapterLLM(MockLLMClient):
            async def chat_json(self, *args, **kwargs):  # noqa: ANN002, ANN003
                return {
                    "nodes": [
                        {"id": "n1", "title": "大纲", "role": "outline", "depends_on": []},
                        {"id": "n2", "title": "研究", "role": "researcher", "depends_on": ["n1"]},
                        {"id": "n3", "title": "第1章：背景", "role": "writer", "depends_on": ["n2"]},
                        {"id": "n4", "title": "第2章：方法", "role": "writer", "depends_on": ["n2"]},
                        {"id": "n5", "title": "一致性检查", "role": "consistency", "depends_on": ["n3", "n4"]},
                    ]
                }

        dag = await decompose_task(
            title="long form ai system report with deep evidence",
            mode="report",
            depth="deep",
            target_words=20000,
            llm_client=_ChapterLLM(),
        )

        writer_titles = [node.title for node in dag.nodes if node.role == "writer"]
        assert any("扩写" in title for title in writer_titles)
        consistency_nodes = [node for node in dag.nodes if node.role == "consistency"]
        assert len(consistency_nodes) == 1
        consistency_deps = set(consistency_nodes[0].depends_on)
        assert "n3" not in consistency_deps
        assert "n4" not in consistency_deps

    @pytest.mark.asyncio
    async def test_decompose_compacts_quick_low_word_dag(self):
        class _WideQuickLLM(MockLLMClient):
            async def chat_json(self, *args, **kwargs):  # noqa: ANN002, ANN003
                return {
                    "nodes": [
                        {"id": "n1", "title": "大纲", "role": "outline", "depends_on": []},
                        {"id": "n2", "title": "研究1", "role": "researcher", "depends_on": ["n1"]},
                        {"id": "n3", "title": "研究2", "role": "researcher", "depends_on": ["n1"]},
                        {"id": "n4", "title": "第1章：背景", "role": "writer", "depends_on": ["n2"]},
                        {"id": "n5", "title": "第2章：方法", "role": "writer", "depends_on": ["n3"]},
                        {"id": "n6", "title": "审查1", "role": "reviewer", "depends_on": ["n4"]},
                        {"id": "n7", "title": "审查2", "role": "reviewer", "depends_on": ["n5"]},
                        {"id": "n8", "title": "一致性检查", "role": "consistency", "depends_on": ["n6", "n7"]},
                    ]
                }

        dag = await decompose_task(
            title="quick smoke convergence",
            mode="report",
            depth="quick",
            target_words=1200,
            llm_client=_WideQuickLLM(),
        )

        roles = [node.role for node in dag.nodes]
        assert roles == ["outline", "researcher", "writer", "reviewer", "consistency"]
        assert len(dag.nodes) == 5
        assert dag.nodes[1].depends_on == [dag.nodes[0].id]
        assert dag.nodes[2].depends_on == [dag.nodes[1].id]
        assert dag.nodes[3].depends_on == [dag.nodes[2].id]
        assert dag.nodes[4].depends_on == [dag.nodes[3].id]

    @pytest.mark.asyncio
    async def test_decompose_enforces_30k_min_primary_chapters(self):
        class _SparseDeepLLM(MockLLMClient):
            async def chat_json(self, *args, **kwargs):  # noqa: ANN002, ANN003
                return {
                    "nodes": [
                        {"id": "n1", "title": "大纲", "role": "outline", "depends_on": []},
                        {"id": "n2", "title": "研究", "role": "researcher", "depends_on": ["n1"]},
                        {"id": "n3", "title": "第1章：背景", "role": "writer", "depends_on": ["n2"]},
                        {"id": "n4", "title": "第2章：方法", "role": "writer", "depends_on": ["n2"]},
                        {"id": "n5", "title": "一致性检查", "role": "consistency", "depends_on": ["n3", "n4"]},
                    ]
                }

        dag = await decompose_task(
            title="ultra long report 30k planning",
            mode="report",
            depth="deep",
            target_words=30000,
            llm_client=_SparseDeepLLM(),
        )
        primary_writers = [
            node for node in dag.nodes
            if node.role == "writer"
            and all(marker not in node.title for marker in ("扩写", "补写", "整合", "篇幅补足"))
        ]
        assert len(primary_writers) >= 10

    @pytest.mark.asyncio
    async def test_decompose_enforces_50k_min_primary_chapters(self):
        class _SparseDeepLLM(MockLLMClient):
            async def chat_json(self, *args, **kwargs):  # noqa: ANN002, ANN003
                return {
                    "nodes": [
                        {"id": "n1", "title": "大纲", "role": "outline", "depends_on": []},
                        {"id": "n2", "title": "研究", "role": "researcher", "depends_on": ["n1"]},
                        {"id": "n3", "title": "第1章：背景", "role": "writer", "depends_on": ["n2"]},
                        {"id": "n4", "title": "第2章：方法", "role": "writer", "depends_on": ["n2"]},
                        {"id": "n5", "title": "一致性检查", "role": "consistency", "depends_on": ["n3", "n4"]},
                    ]
                }

        dag = await decompose_task(
            title="ultra long report 50k planning",
            mode="report",
            depth="deep",
            target_words=50000,
            llm_client=_SparseDeepLLM(),
        )
        primary_writers = [
            node for node in dag.nodes
            if node.role == "writer"
            and all(marker not in node.title for marker in ("扩写", "补写", "整合", "篇幅补足"))
        ]
        assert len(primary_writers) >= 14

    @pytest.mark.asyncio
    async def test_decompose_does_not_compact_quick_when_target_not_short(self):
        class _WideQuickLLM(MockLLMClient):
            async def chat_json(self, *args, **kwargs):  # noqa: ANN002, ANN003
                return {
                    "nodes": [
                        {"id": "n1", "title": "大纲", "role": "outline", "depends_on": []},
                        {"id": "n2", "title": "研究", "role": "researcher", "depends_on": ["n1"]},
                        {"id": "n3", "title": "第1章：背景", "role": "writer", "depends_on": ["n2"]},
                        {"id": "n4", "title": "第1章审查", "role": "reviewer", "depends_on": ["n3"]},
                        {"id": "n5", "title": "第2章：方法", "role": "writer", "depends_on": ["n2"]},
                        {"id": "n6", "title": "第2章审查", "role": "reviewer", "depends_on": ["n5"]},
                        {"id": "n7", "title": "一致性检查", "role": "consistency", "depends_on": ["n4", "n6"]},
                    ]
                }

        dag = await decompose_task(
            title="quick but not short target",
            mode="report",
            depth="quick",
            target_words=4000,
            llm_client=_WideQuickLLM(),
        )

        assert len(dag.nodes) >= 7


class TestDecomposeTask:
    @pytest.mark.asyncio
    async def test_successful_decomposition_with_overrides(self):
        mock_llm = MockLLMClient()
        dag = await decompose_task(
            title="quantum computing technical report with full analysis",
            mode="report",
            depth="standard",
            target_words=10000,
            llm_client=mock_llm,
            model="gpt-4o",
            max_retries=2,
            fallback_models=["deepseek-chat"],
        )
        assert len(dag.nodes) >= 1
        assert dag.nodes[0].role == "outline"

        json_calls = [c for c in mock_llm.call_log if c["method"] == "chat_json"]
        assert len(json_calls) == 1
        assert json_calls[0]["role"] == "orchestrator"
        assert json_calls[0]["model"] == "gpt-4o"
        assert json_calls[0]["max_retries"] == 2
        assert json_calls[0]["fallback_models"] == ["deepseek-chat"]

    @pytest.mark.asyncio
    async def test_validation_error_on_bad_input(self):
        mock_llm = MockLLMClient()
        with pytest.raises(TaskValidationError):
            await decompose_task(
                title="tiny",
                mode="report",
                depth="standard",
                target_words=10000,
                llm_client=mock_llm,
            )
        assert len(mock_llm.call_log) == 0

    @pytest.mark.asyncio
    async def test_target_words_passed_to_prompt(self):
        mock_llm = MockLLMClient()
        await decompose_task(
            title="quantum computing technical report with full analysis",
            mode="report",
            depth="deep",
            target_words=20000,
            llm_client=mock_llm,
        )
        json_calls = [c for c in mock_llm.call_log if c["method"] == "chat_json"]
        prompt_content = json_calls[0]["messages"][-1]["content"]
        assert "20000" in prompt_content
        assert "deep" in prompt_content

    @pytest.mark.asyncio
    async def test_fallback_dag_when_llm_returns_invalid_json(self):
        class _BrokenLLM(MockLLMClient):
            async def chat_json(self, *args, **kwargs):  # noqa: ANN002, ANN003
                raise ValueError("LLM returned invalid JSON")

        dag = await decompose_task(
            title="high availability deployment runbook generation",
            mode="report",
            depth="standard",
            target_words=8000,
            llm_client=_BrokenLLM(),
        )

        assert len(dag.nodes) >= 4
        assert dag.nodes[0].role == "outline"
        researcher_nodes = [node for node in dag.nodes if node.role == "researcher"]
        writer_nodes = [node for node in dag.nodes if node.role == "writer"]
        reviewer_nodes = [node for node in dag.nodes if node.role == "reviewer"]
        assert researcher_nodes
        assert writer_nodes
        assert reviewer_nodes
        assert any(dag.nodes[0].id in node.depends_on for node in researcher_nodes)
