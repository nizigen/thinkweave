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
