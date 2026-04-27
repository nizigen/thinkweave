"""Tests for Step 4.4 Knowledge Graph (TDD RED phase)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


# ===========================================================================
# 1. KnowledgeGraph — add_entry / query / prune_stale
# ===========================================================================

class TestKnowledgeGraph:
    """KnowledgeGraph core CRUD and TTL pruning."""

    def test_add_entry_stores_item(self):
        from app.memory.knowledge.graph import KnowledgeGraph, KGEntry
        kg = KnowledgeGraph()
        entry = KGEntry(
            key="quantum_computing",
            content="Quantum computing uses qubits.",
            credibility=0.9,
        )
        kg.add_entry(entry)
        assert kg.size() == 1

    def test_query_returns_matching_entries(self):
        from app.memory.knowledge.graph import KnowledgeGraph, KGEntry
        kg = KnowledgeGraph()
        kg.add_entry(KGEntry(key="qc", content="Quantum computing overview.", credibility=0.8))
        kg.add_entry(KGEntry(key="ml", content="Machine learning basics.", credibility=0.85))
        results = kg.query("quantum")
        assert len(results) >= 1
        assert any("quantum" in r.content.lower() for r in results)

    def test_query_empty_returns_empty_list(self):
        from app.memory.knowledge.graph import KnowledgeGraph
        kg = KnowledgeGraph()
        assert kg.query("anything") == []

    def test_prune_stale_removes_expired_entries(self):
        from app.memory.knowledge.graph import KnowledgeGraph, KGEntry
        kg = KnowledgeGraph(ttl_days=90)
        old_entry = KGEntry(
            key="stale",
            content="Old knowledge.",
            credibility=0.9,
            created_at=datetime.now(UTC) - timedelta(days=91),
        )
        fresh_entry = KGEntry(
            key="fresh",
            content="Recent knowledge.",
            credibility=0.9,
        )
        kg.add_entry(old_entry)
        kg.add_entry(fresh_entry)
        pruned = kg.prune_stale()
        assert pruned == 1
        assert kg.size() == 1
        assert kg.query("recent")[0].key == "fresh"

    def test_add_entry_deduplicates_by_key(self):
        from app.memory.knowledge.graph import KnowledgeGraph, KGEntry
        kg = KnowledgeGraph()
        kg.add_entry(KGEntry(key="qc", content="Version 1.", credibility=0.7))
        kg.add_entry(KGEntry(key="qc", content="Version 2.", credibility=0.9))
        assert kg.size() == 1
        results = kg.query("Version")
        # Higher credibility version should win
        assert results[0].credibility == 0.9

    def test_to_context_string_returns_formatted_text(self):
        from app.memory.knowledge.graph import KnowledgeGraph, KGEntry
        kg = KnowledgeGraph()
        kg.add_entry(KGEntry(key="qc", content="Quantum computing uses qubits.", credibility=0.9))
        text = kg.to_context_string(limit=5)
        assert "Quantum" in text
        assert len(text) > 0


# ===========================================================================
# 2. KGPromotion — Session→KG data promotion
# ===========================================================================

class TestKGPromotion:
    """promote_session() filters credibility >= threshold and promotes to KG."""

    @pytest.mark.asyncio
    async def test_promote_filters_low_credibility(self):
        from app.memory.knowledge.graph import KnowledgeGraph
        from app.memory.knowledge.promotion import promote_session

        kg = KnowledgeGraph()
        entries = [
            {"key": "high", "content": "High quality fact.", "credibility": 0.8},
            {"key": "low", "content": "Low quality guess.", "credibility": 0.5},
            {"key": "borderline", "content": "Borderline fact.", "credibility": 0.7},
        ]
        promoted = await promote_session(entries, kg, credibility_threshold=0.7)
        assert promoted == 2  # high + borderline
        assert kg.size() == 2

    @pytest.mark.asyncio
    async def test_promote_empty_entries_returns_zero(self):
        from app.memory.knowledge.graph import KnowledgeGraph
        from app.memory.knowledge.promotion import promote_session

        kg = KnowledgeGraph()
        promoted = await promote_session([], kg)
        assert promoted == 0
        assert kg.size() == 0

    @pytest.mark.asyncio
    async def test_promote_returns_count_of_promoted(self):
        from app.memory.knowledge.graph import KnowledgeGraph
        from app.memory.knowledge.promotion import promote_session

        kg = KnowledgeGraph()
        entries = [
            {"key": f"fact_{i}", "content": f"Fact {i}.", "credibility": 0.9}
            for i in range(5)
        ]
        promoted = await promote_session(entries, kg)
        assert promoted == 5
        assert kg.size() == 5


# ===========================================================================
# 3. SessionMemory.cleanup() with KG promotion
# ===========================================================================

class TestSessionCleanupWithKG:
    """cleanup() accepts optional kg and calls promote when write_count > 0."""

    @pytest.mark.asyncio
    async def test_cleanup_with_kg_returns_promotion_ready_true(self):
        from app.memory.session import SessionMemory
        from app.memory.knowledge.graph import KnowledgeGraph

        # Use disabled adapter so no real cognee calls
        from app.memory.config import MemoryConfig
        from app.memory.adapter import MemoryAdapter
        cfg = MemoryConfig(memory_enabled=False)
        adapter = MemoryAdapter(config=cfg)

        sm = SessionMemory(task_id="test-task-99", adapter=adapter)
        await sm.initialize()
        sm._write_count = 3  # simulate writes

        kg = KnowledgeGraph()
        result = await sm.cleanup(kg=kg)
        assert result["promotion_ready"] is False  # disabled adapter
        assert "write_count" in result

    @pytest.mark.asyncio
    async def test_cleanup_without_kg_still_works(self):
        from app.memory.session import SessionMemory
        from app.memory.config import MemoryConfig
        from app.memory.adapter import MemoryAdapter
        cfg = MemoryConfig(memory_enabled=False)
        adapter = MemoryAdapter(config=cfg)

        sm = SessionMemory(task_id="test-task-100", adapter=adapter)
        await sm.initialize()
        result = await sm.cleanup()
        assert "task_id" in result


# ===========================================================================
# 4. MemoryMiddleware KG context injection for outline/writer
# ===========================================================================

class TestMemoryMiddlewareKGInjection:
    """MemoryMiddleware injects KG context for outline and writer roles."""

    @pytest.mark.asyncio
    async def test_outline_agent_receives_kg_context(self):
        from app.agents.middleware import MemoryMiddleware
        from app.memory.knowledge.graph import KnowledgeGraph, KGEntry

        kg = KnowledgeGraph()
        kg.add_entry(KGEntry(key="qc", content="Quantum fact from KG.", credibility=0.85))

        middleware = MemoryMiddleware(knowledge_graph=kg)

        agent = MagicMock()
        agent.role = "outline"

        ctx = {"task_id": "task-42", "title": "Quantum Computing Report", "payload": {}}
        result_ctx = await middleware.before_task(agent, ctx)

        assert "kg_context" in result_ctx
        assert "Quantum fact from KG." in result_ctx["kg_context"]

    @pytest.mark.asyncio
    async def test_writer_agent_receives_kg_context(self):
        from app.agents.middleware import MemoryMiddleware
        from app.memory.knowledge.graph import KnowledgeGraph, KGEntry

        kg = KnowledgeGraph()
        kg.add_entry(KGEntry(key="qubit", content="Qubit is a quantum bit.", credibility=0.9))

        middleware = MemoryMiddleware(knowledge_graph=kg)

        agent = MagicMock()
        agent.role = "writer"

        ctx = {"task_id": "task-43", "title": "Chapter 1", "payload": {"chapter_title": "Qubits"}}
        result_ctx = await middleware.before_task(agent, ctx)

        assert "kg_context" in result_ctx
        assert "Qubit" in result_ctx["kg_context"]

    @pytest.mark.asyncio
    async def test_reviewer_agent_does_not_receive_kg_context(self):
        from app.agents.middleware import MemoryMiddleware
        from app.memory.knowledge.graph import KnowledgeGraph, KGEntry

        kg = KnowledgeGraph()
        kg.add_entry(KGEntry(key="fact", content="Some fact.", credibility=0.9))

        middleware = MemoryMiddleware(knowledge_graph=kg)

        agent = MagicMock()
        agent.role = "reviewer"

        ctx = {"task_id": "task-44", "payload": {}}
        result_ctx = await middleware.before_task(agent, ctx)

        # reviewer should not get KG context (not needed for review)
        assert result_ctx.get("kg_context", "") == ""

    @pytest.mark.asyncio
    async def test_middleware_without_kg_sets_empty_kg_context(self):
        from app.agents.middleware import MemoryMiddleware

        middleware = MemoryMiddleware()  # no kg

        agent = MagicMock()
        agent.role = "outline"

        ctx = {"task_id": "task-45", "payload": {}}
        result_ctx = await middleware.before_task(agent, ctx)

        assert result_ctx.get("kg_context", "") == ""
