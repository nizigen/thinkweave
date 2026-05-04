from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.agents.consistency_agent import ConsistencyAgent
from app.agents.outline_agent import OutlineAgent
from app.agents.researcher_agent import ResearcherAgent
from app.agents.reviewer_agent import ReviewerAgent
from app.agents.writer_agent import WriterAgent
from app.services.runtime_bootstrap import set_runtime_mcp_client


class MockLLMClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.tool_responses: list[dict[str, Any]] = []

    async def chat(
        self,
        messages,
        *,
        model=None,
        role=None,
        max_tokens=None,
        temperature=0.7,
        max_retries=None,
        fallback_models=None,
    ):
        self.calls.append(
            {
                "messages": messages,
                "role": role,
                "model": model,
                "max_retries": max_retries,
                "fallback_models": fallback_models,
            }
        )
        return "ok"

    async def chat_with_tools(
        self,
        messages,
        tools,
        *,
        model=None,
        role=None,
        max_tokens=None,
        max_retries=None,
        fallback_models=None,
    ):
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "role": role,
                "model": model,
                "method": "chat_with_tools",
            }
        )
        if self.tool_responses:
            return self.tool_responses.pop(0)
        return {"type": "text", "content": "mock tool response"}


class _MockToolRegistry:
    def to_openai_tools(self, tool_names=None):
        return [
            {
                "type": "function",
                "function": {
                    "name": "web.search",
                    "description": "search",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]


class _MockMCPClient:
    def __init__(self) -> None:
        self.registry = _MockToolRegistry()
        self.calls: list[dict[str, Any]] = []

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        self.calls.append({"tool_name": tool_name, "arguments": arguments})
        return "tool-result"


@pytest.mark.asyncio
async def test_outline_agent_normalizes_extended_outline_contract():
    llm = MockLLMClient()
    agent = OutlineAgent(
        agent_id=uuid.uuid4(),
        name="outline-1",
        llm_client=llm,
        middlewares=(),
    )

    result = await agent.handle_task(
        {
            "task_id": "t1",
            "title": "Generate outline",
            "payload": {
                "title": "AI Report",
                "mode": "report",
                "target_words": 8000,
                "draft_text": "Existing partial draft",
                "review_comments": "Please strengthen the methodology chapter.",
                "style_requirements": "formal and technical",
            },
        }
    )

    assert result == "ok"
    assert llm.calls[-1]["role"] == "outline"
    user_prompt = llm.calls[-1]["messages"][-1]["content"]
    assert "topic_claims" in user_prompt
    assert "Existing partial draft" in user_prompt
    assert "formal and technical" in user_prompt


@pytest.mark.asyncio
async def test_writer_agent_injects_memory_topic_claims_and_evidence_into_prompt():
    llm = MockLLMClient()
    agent = WriterAgent(
        agent_id=uuid.uuid4(),
        name="writer-1",
        llm_client=llm,
        middlewares=(),
    )

    await agent.handle_task(
        {
            "task_id": "t1",
            "title": "Write chapter",
            "memory_context": "Do not repeat intro section",
            "payload": {
                "chapter_index": 1,
                "chapter_title": "Intro",
                "full_outline": "1. Intro",
                "chapter_description": "Describe the context",
                "context_bridges": "Connect from abstract",
                "topic_claims": {
                    "owns": ["problem framing"],
                    "boundary": ["do not write methods"],
                },
                "assigned_evidence": ["Smith 2024", "Chen 2025"],
                "target_words": 1200,
            },
        }
    )

    assert llm.calls[0]["role"] == "writer"
    user_prompt = llm.calls[0]["messages"][-1]["content"]
    assert "Do not repeat intro section" in user_prompt
    assert "problem framing" in user_prompt
    assert "Smith 2024" in user_prompt


@pytest.mark.asyncio
async def test_researcher_agent_supplies_source_scope_and_keyword_plan():
    llm = MockLLMClient()
    agent = ResearcherAgent(
        agent_id=uuid.uuid4(),
        name="researcher-1",
        llm_client=llm,
        middlewares=(),
    )

    await agent.handle_task(
        {
            "task_id": "t1",
            "title": "Research plan",
            "memory_context": "avoid non-peer-reviewed sources",
            "payload": {
                "title": "AI report",
                "mode": "report",
                "full_outline": "1. Intro\n2. Methods",
                "source_policy": "{\"allow\": [\"peer-reviewed journals\"]}",
                "research_keywords": "ai safety, benchmark, regulation",
                "target_words": 8000,
            },
        }
    )

    assert llm.calls[0]["role"] == "researcher"
    user_prompt = llm.calls[0]["messages"][-1]["content"]
    assert "source policy" in user_prompt.lower()
    assert "keyword_plan" in user_prompt
    assert "evidence_ledger" in user_prompt


@pytest.mark.asyncio
async def test_researcher_agent_uses_tool_backed_path_when_mcp_available():
    llm = MockLLMClient()
    llm.tool_responses = [
        {
            "type": "tool_calls",
            "tool_calls": [
                {
                    "id": "call-1",
                    "function": {"name": "web.search", "arguments": "{\"q\": \"ai safety\"}"},
                }
            ],
        },
        {
            "type": "text",
            "content": (
                "{"
                "\"topic_anchor\":\"AI safety governance\","
                "\"source_scope\":{\"allowed\":[\"paper\"],\"disallowed\":[],\"time_window\":\"2020-2026\"},"
                "\"keyword_plan\":[{\"bucket\":\"regulation\",\"queries\":[\"ai safety regulation\"]}],"
                "\"evidence_ledger\":[{\"evidence_id\":\"E1\",\"claim_target\":\"policy trend\","
                "\"required_source_type\":\"official_report\",\"priority\":\"high\","
                "\"source_url\":\"https://example.com/report\",\"source_title\":\"Example Report\","
                "\"published_at\":\"2026-01-01\"}],"
                "\"chapter_mapping\":[{\"chapter_hint\":\"治理框架\",\"must_have_evidence_ids\":[\"E1\"],\"boundary_notes\":[]}],"
                "\"uncertainty_flags\":[]"
                "}"
            ),
        },
    ]
    mcp_client = _MockMCPClient()
    set_runtime_mcp_client(mcp_client)
    try:
        agent = ResearcherAgent(
            agent_id=uuid.uuid4(),
            name="researcher-tools",
            llm_client=llm,
            middlewares=(),
        )

        result = await agent.handle_task(
            {
                "task_id": "t1",
                "title": "Research with tools",
                "payload": {
                    "title": "AI report",
                    "mode": "report",
                    "depth": "standard",
                    "full_outline": "1. Intro\n2. Governance",
                    "source_policy": "{\"allow\": [\"official reports\"]}",
                    "research_keywords": "ai safety, governance",
                    "target_words": 10000,
                },
            }
        )
        assert "evidence_ledger" in result
        assert any(call.get("method") == "chat_with_tools" for call in llm.calls)
        assert len(mcp_client.calls) == 1
        assert mcp_client.calls[0]["tool_name"] == "web.search"
    finally:
        set_runtime_mcp_client(None)


@pytest.mark.asyncio
async def test_reviewer_agent_supplies_scope_and_overlap_fields():
    llm = MockLLMClient()
    agent = ReviewerAgent(
        agent_id=uuid.uuid4(),
        name="reviewer-1",
        llm_client=llm,
        middlewares=(),
    )

    await agent.handle_task(
        {
            "task_id": "t1",
            "title": "Review chapter",
            "payload": {
                "chapter_index": 1,
                "chapter_title": "Intro",
                "chapter_content": "content",
                "chapter_description": "desc",
                "topic_claims": {"owns": ["background"], "boundary": ["results"]},
                "assigned_evidence": ["Smith 2024"],
            },
        }
    )

    assert llm.calls[0]["role"] == "reviewer"
    user_prompt = llm.calls[0]["messages"][-1]["content"]
    assert "overlap_findings" in user_prompt
    assert "background" in user_prompt
    assert "Smith 2024" in user_prompt


@pytest.mark.asyncio
async def test_reviewer_agent_enforces_evidence_dimensions_and_blocks_pass_on_low_scores():
    llm = MockLLMClient()
    llm.chat = AsyncMock(
        return_value=json.dumps(
            {
                "score": 88,
                "must_fix": [],
                "feedback": "ok",
                "pass": True,
                "accuracy_score": 80,
                "coherence_score": 80,
                "evidence_sufficiency_score": 55,
                "boundary_compliance_score": 80,
                "non_overlap_score": 80,
                "specificity_score": 58,
                "source_attribution_score": 59,
                "strongest_counterargument": "counter",
            },
            ensure_ascii=False,
        )
    )
    agent = ReviewerAgent(
        agent_id=uuid.uuid4(),
        name="reviewer-policy",
        llm_client=llm,
        middlewares=(),
    )

    result = await agent.handle_task(
        {
            "task_id": "t1",
            "title": "Review chapter",
            "payload": {
                "chapter_index": 1,
                "chapter_title": "Intro",
                "chapter_content": "content",
            },
        }
    )
    parsed = json.loads(result)
    assert parsed["pass"] is False
    assert parsed["score"] <= 59
    assert "unsupported_claims" in parsed
    assert "missing_sources" in parsed
    assert len(parsed["must_fix"]) >= 1


@pytest.mark.asyncio
async def test_consistency_agent_normalizes_extended_document_contract():
    llm = MockLLMClient()
    agent = ConsistencyAgent(
        agent_id=uuid.uuid4(),
        name="consistency-1",
        llm_client=llm,
        middlewares=(),
    )

    await agent.handle_task(
        {
            "task_id": "t1",
            "title": "Consistency check",
            "payload": {
                "chapters_summary": "summary",
                "full_text": "full text",
                "topic_claims": [{"chapter_index": 1, "owns": ["claim-a"]}],
                "chapter_metadata": [{"chapter_index": 1, "word_count": 1200}],
            },
        }
    )

    assert llm.calls[0]["role"] == "consistency"
    user_prompt = llm.calls[0]["messages"][-1]["content"]
    assert "claim-a" in user_prompt
    assert "word_count" in user_prompt
