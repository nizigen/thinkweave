"""Tests for Task API - Step 2.3"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.main import app
from app.routers.tasks import get_llm_client
from tests.conftest import MockLLMClient


VALID_PAYLOAD = {
    "title": "Quantum computing report generation task",
    "mode": "report",
    "depth": "standard",
    "target_words": 10000,
}


class TestCreateTask:
    @pytest.fixture(autouse=True)
    def _override_llm(self, mock_llm: MockLLMClient):
        app.dependency_overrides[get_llm_client] = lambda: mock_llm
        yield
        app.dependency_overrides.pop(get_llm_client, None)

    async def test_create_task_success(self, client: AsyncClient, mock_llm: MockLLMClient):
        resp = await client.post("/api/tasks", json=VALID_PAYLOAD)
        assert resp.status_code == 201
        data = resp.json()

        assert data["title"] == VALID_PAYLOAD["title"]
        assert data["mode"] == "report"
        assert data["depth"] == "standard"
        assert data["target_words"] == 10000
        assert data["status"] == "pending"
        assert data["fsm_state"] == "init"

        assert len(data["nodes"]) == 3
        roles = {n["agent_role"] for n in data["nodes"]}
        assert "outline" in roles
        assert "writer" in roles

        assert any(c["role"] == "orchestrator" for c in mock_llm.call_log)

    async def test_create_task_with_novel_mode(self, client: AsyncClient):
        payload = {**VALID_PAYLOAD, "mode": "novel", "target_words": 50000}
        resp = await client.post("/api/tasks", json=payload)
        assert resp.status_code == 201
        assert resp.json()["mode"] == "novel"

    async def test_create_task_title_too_short(self, client: AsyncClient):
        payload = {**VALID_PAYLOAD, "title": "short"}
        resp = await client.post("/api/tasks", json=payload)
        assert resp.status_code == 422

    async def test_create_task_invalid_mode(self, client: AsyncClient):
        payload = {**VALID_PAYLOAD, "mode": "invalid"}
        resp = await client.post("/api/tasks", json=payload)
        assert resp.status_code == 422

    async def test_create_task_invalid_depth(self, client: AsyncClient):
        payload = {**VALID_PAYLOAD, "depth": "ultra_deep"}
        resp = await client.post("/api/tasks", json=payload)
        assert resp.status_code == 422

    async def test_create_task_target_words_too_low(self, client: AsyncClient):
        payload = {**VALID_PAYLOAD, "target_words": 100}
        resp = await client.post("/api/tasks", json=payload)
        assert resp.status_code == 422

    async def test_create_task_target_words_too_high(self, client: AsyncClient):
        payload = {**VALID_PAYLOAD, "target_words": 300000}
        resp = await client.post("/api/tasks", json=payload)
        assert resp.status_code == 422

    async def test_create_task_default_values(self, client: AsyncClient):
        payload = {"title": "Default value task title long enough"}
        resp = await client.post("/api/tasks", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["mode"] == "report"
        assert data["depth"] == "standard"
        assert data["target_words"] == 10000

    async def test_create_task_with_draft_text_enters_pre_review_integrity(
        self, client: AsyncClient
    ):
        payload = {**VALID_PAYLOAD, "draft_text": "Existing draft content"}
        resp = await client.post("/api/tasks", json=payload)
        assert resp.status_code == 201
        assert resp.json()["fsm_state"] == "pre_review_integrity"

    async def test_create_task_with_review_comments_enters_pre_review_integrity(
        self, client: AsyncClient
    ):
        payload = {
            **VALID_PAYLOAD,
            "review_comments": "Please fix unsupported claims.",
        }
        resp = await client.post("/api/tasks", json=payload)
        assert resp.status_code == 201
        assert resp.json()["fsm_state"] == "pre_review_integrity"

    async def test_create_task_nodes_have_correct_dependencies(self, client: AsyncClient):
        resp = await client.post("/api/tasks", json=VALID_PAYLOAD)
        assert resp.status_code == 201
        nodes = resp.json()["nodes"]

        outline_node = next(n for n in nodes if n["agent_role"] == "outline")
        assert outline_node["depends_on"] is None or outline_node["depends_on"] == []

        writer_nodes = [n for n in nodes if n["agent_role"] == "writer"]
        for wn in writer_nodes:
            assert wn["depends_on"] is not None
            assert len(wn["depends_on"]) > 0


class TestGetTask:
    @pytest.fixture(autouse=True)
    def _override_llm(self, mock_llm: MockLLMClient):
        app.dependency_overrides[get_llm_client] = lambda: mock_llm
        yield
        app.dependency_overrides.pop(get_llm_client, None)

    async def test_get_task_success(self, client: AsyncClient):
        create_resp = await client.post("/api/tasks", json=VALID_PAYLOAD)
        task_id = create_resp.json()["id"]

        resp = await client.get(f"/api/tasks/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == task_id
        assert data["title"] == VALID_PAYLOAD["title"]
        assert len(data["nodes"]) == 3

    async def test_get_task_not_found(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/tasks/{fake_id}")
        assert resp.status_code == 404

    async def test_get_task_invalid_uuid(self, client: AsyncClient):
        resp = await client.get("/api/tasks/not-a-uuid")
        assert resp.status_code == 422


class TestListTasks:
    @pytest.fixture(autouse=True)
    def _override_llm(self, mock_llm: MockLLMClient):
        app.dependency_overrides[get_llm_client] = lambda: mock_llm
        yield
        app.dependency_overrides.pop(get_llm_client, None)

    async def test_list_tasks_empty(self, client: AsyncClient):
        resp = await client.get("/api/tasks")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_list_tasks_after_create(self, client: AsyncClient):
        create_resp = await client.post("/api/tasks", json=VALID_PAYLOAD)
        created_id = create_resp.json()["id"]

        resp = await client.get("/api/tasks")
        assert resp.status_code == 200
        ids = [t["id"] for t in resp.json()]
        assert created_id in ids

    async def test_list_tasks_no_nodes_field(self, client: AsyncClient):
        await client.post("/api/tasks", json=VALID_PAYLOAD)
        resp = await client.get("/api/tasks")
        assert resp.status_code == 200
        for t in resp.json():
            assert "nodes" not in t

    async def test_list_tasks_ordered_newest_first(self, client: AsyncClient):
        r1 = await client.post(
            "/api/tasks",
            json={**VALID_PAYLOAD, "title": "First task ordering check"},
        )
        r2 = await client.post(
            "/api/tasks",
            json={**VALID_PAYLOAD, "title": "Second task ordering check"},
        )
        id1 = r1.json()["id"]
        id2 = r2.json()["id"]

        resp = await client.get("/api/tasks")
        ids = [t["id"] for t in resp.json()]
        assert ids.index(id2) < ids.index(id1)
