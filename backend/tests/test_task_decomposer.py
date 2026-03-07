"""Tests for task_decomposer — TDD RED phase first."""

from __future__ import annotations

import pytest

from app.schemas.task import (
    DAGNodeSchema,
    DAGSchema,
    ValidationResult,
    VALID_MODES,
    VALID_DEPTHS,
)
from app.services.task_decomposer import (
    CyclicDAGError,
    TaskValidationError,
    validate_task_input,
    validate_dag_acyclic,
    parse_dag_response,
    decompose_task,
)
from tests.conftest import MockLLMClient


# ---------------------------------------------------------------------------
# validate_task_input
# ---------------------------------------------------------------------------

class TestValidateTaskInput:
    def test_valid_input(self):
        result = validate_task_input("量子计算技术报告", "report", "standard")
        assert result.ok is True
        assert result.issues == []

    def test_title_too_short(self):
        result = validate_task_input("短", "report", "standard")
        assert result.ok is False
        assert any("标题" in issue or "title" in issue.lower() for issue in result.issues)

    def test_empty_title(self):
        result = validate_task_input("", "report", "standard")
        assert result.ok is False

    def test_whitespace_only_title(self):
        result = validate_task_input("   ", "report", "standard")
        assert result.ok is False

    def test_invalid_mode(self):
        result = validate_task_input("量子计算技术报告", "invalid_mode", "standard")
        assert result.ok is False
        assert any("mode" in issue.lower() or "模式" in issue for issue in result.issues)

    def test_invalid_depth(self):
        result = validate_task_input("量子计算技术报告", "report", "ultra_deep")
        assert result.ok is False
        assert any("depth" in issue.lower() or "深度" in issue for issue in result.issues)

    def test_all_valid_modes(self):
        for mode in VALID_MODES:
            result = validate_task_input("量子计算技术报告写作任务", mode, "standard")
            assert result.ok is True, f"Mode '{mode}' should be valid"

    def test_all_valid_depths(self):
        for depth in VALID_DEPTHS:
            result = validate_task_input("量子计算技术报告写作任务", "report", depth)
            assert result.ok is True, f"Depth '{depth}' should be valid"

    def test_multiple_issues(self):
        result = validate_task_input("短", "bad", "bad")
        assert result.ok is False
        assert len(result.issues) >= 2


# ---------------------------------------------------------------------------
# validate_dag_acyclic
# ---------------------------------------------------------------------------

class TestValidateDAGAcyclic:
    def test_valid_linear_dag(self):
        dag = DAGSchema(nodes=[
            DAGNodeSchema(id="n1", title="大纲", role="outline", depends_on=[]),
            DAGNodeSchema(id="n2", title="写作", role="writer", depends_on=["n1"]),
            DAGNodeSchema(id="n3", title="审查", role="reviewer", depends_on=["n2"]),
        ])
        validate_dag_acyclic(dag)  # Should not raise

    def test_valid_parallel_dag(self):
        dag = DAGSchema(nodes=[
            DAGNodeSchema(id="n1", title="大纲", role="outline", depends_on=[]),
            DAGNodeSchema(id="n2", title="第1章", role="writer", depends_on=["n1"]),
            DAGNodeSchema(id="n3", title="第2章", role="writer", depends_on=["n1"]),
            DAGNodeSchema(id="n4", title="一致性", role="consistency", depends_on=["n2", "n3"]),
        ])
        validate_dag_acyclic(dag)  # Should not raise

    def test_self_cycle(self):
        dag = DAGSchema(nodes=[
            DAGNodeSchema(id="n1", title="大纲", role="outline", depends_on=["n1"]),
        ])
        with pytest.raises(CyclicDAGError):
            validate_dag_acyclic(dag)

    def test_two_node_cycle(self):
        dag = DAGSchema(nodes=[
            DAGNodeSchema(id="n1", title="节点1", role="outline", depends_on=["n2"]),
            DAGNodeSchema(id="n2", title="节点2", role="writer", depends_on=["n1"]),
        ])
        with pytest.raises(CyclicDAGError):
            validate_dag_acyclic(dag)

    def test_three_node_cycle(self):
        dag = DAGSchema(nodes=[
            DAGNodeSchema(id="n1", title="节点1", role="outline", depends_on=["n3"]),
            DAGNodeSchema(id="n2", title="节点2", role="writer", depends_on=["n1"]),
            DAGNodeSchema(id="n3", title="节点3", role="reviewer", depends_on=["n2"]),
        ])
        with pytest.raises(CyclicDAGError):
            validate_dag_acyclic(dag)

    def test_unknown_dependency(self):
        dag = DAGSchema(nodes=[
            DAGNodeSchema(id="n1", title="大纲", role="outline", depends_on=["n999"]),
        ])
        with pytest.raises(CyclicDAGError, match="unknown"):
            validate_dag_acyclic(dag)

    def test_empty_dag_rejected_by_schema(self):
        with pytest.raises(Exception):
            DAGSchema(nodes=[])


# ---------------------------------------------------------------------------
# parse_dag_response
# ---------------------------------------------------------------------------

class TestParseDAGResponse:
    def test_valid_response(self):
        raw = {
            "nodes": [
                {"id": "n1", "title": "大纲", "role": "outline", "depends_on": []},
                {"id": "n2", "title": "写作", "role": "writer", "depends_on": ["n1"]},
            ]
        }
        dag = parse_dag_response(raw)
        assert len(dag.nodes) == 2
        assert dag.nodes[0].id == "n1"
        assert dag.nodes[1].depends_on == ["n1"]

    def test_invalid_role_rejected(self):
        raw = {
            "nodes": [
                {"id": "n1", "title": "坏节点", "role": "hacker", "depends_on": []},
            ]
        }
        with pytest.raises(ValueError):
            parse_dag_response(raw)

    def test_missing_nodes_key(self):
        raw = {"data": []}
        with pytest.raises(ValueError):
            parse_dag_response(raw)

    def test_duplicate_node_ids(self):
        raw = {
            "nodes": [
                {"id": "n1", "title": "节点1", "role": "outline", "depends_on": []},
                {"id": "n1", "title": "节点2", "role": "writer", "depends_on": []},
            ]
        }
        with pytest.raises(ValueError, match="[Dd]uplicate"):
            parse_dag_response(raw)

    def test_first_node_must_be_outline(self):
        raw = {
            "nodes": [
                {"id": "n1", "title": "写作", "role": "writer", "depends_on": []},
            ]
        }
        with pytest.raises(ValueError, match="[Oo]utline"):
            parse_dag_response(raw)


# ---------------------------------------------------------------------------
# decompose_task (integration with MockLLMClient)
# ---------------------------------------------------------------------------

class TestDecomposeTask:
    @pytest.mark.asyncio
    async def test_successful_decomposition(self):
        mock_llm = MockLLMClient()
        dag = await decompose_task(
            title="量子计算技术报告的完整研究分析",
            mode="report",
            depth="standard",
            target_words=10000,
            llm_client=mock_llm,
        )
        assert len(dag.nodes) >= 1
        assert dag.nodes[0].role == "outline"

        # Verify LLM was called with orchestrator role
        json_calls = [c for c in mock_llm.call_log if c["method"] == "chat_json"]
        assert len(json_calls) == 1
        assert json_calls[0]["role"] == "orchestrator"

    @pytest.mark.asyncio
    async def test_validation_error_on_bad_input(self):
        mock_llm = MockLLMClient()
        with pytest.raises(TaskValidationError):
            await decompose_task(
                title="短",
                mode="report",
                depth="standard",
                target_words=10000,
                llm_client=mock_llm,
            )
        # LLM should NOT have been called
        assert len(mock_llm.call_log) == 0

    @pytest.mark.asyncio
    async def test_validation_error_on_bad_mode(self):
        mock_llm = MockLLMClient()
        with pytest.raises(TaskValidationError):
            await decompose_task(
                title="量子计算技术报告的完整研究分析",
                mode="podcast",
                depth="standard",
                target_words=10000,
                llm_client=mock_llm,
            )

    @pytest.mark.asyncio
    async def test_target_words_passed_to_prompt(self):
        mock_llm = MockLLMClient()
        await decompose_task(
            title="量子计算技术报告的完整研究分析",
            mode="report",
            depth="deep",
            target_words=20000,
            llm_client=mock_llm,
        )
        json_calls = [c for c in mock_llm.call_log if c["method"] == "chat_json"]
        prompt_content = json_calls[0]["messages"][-1]["content"]
        assert "20000" in prompt_content
        assert "deep" in prompt_content


# ---------------------------------------------------------------------------
# DAGSchema Pydantic validation
# ---------------------------------------------------------------------------

class TestDAGSchemaValidation:
    def test_valid_node(self):
        node = DAGNodeSchema(id="n1", title="test", role="outline", depends_on=[])
        assert node.role == "outline"

    def test_invalid_role(self):
        with pytest.raises(Exception):
            DAGNodeSchema(id="n1", title="test", role="invalid", depends_on=[])

    def test_empty_id_rejected(self):
        with pytest.raises(Exception):
            DAGNodeSchema(id="", title="test", role="outline", depends_on=[])

    def test_empty_title_rejected(self):
        with pytest.raises(Exception):
            DAGNodeSchema(id="n1", title="", role="outline", depends_on=[])
