"""Tests for Task API — Step 2.3"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.routers.tasks import get_llm_client
from app.main import app
from tests.conftest import MockLLMClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_PAYLOAD = {
    "title": "量子计算技术报告写作",
    "mode": "report",
    "depth": "standard",
    "target_words": 10000,
}


# ---------------------------------------------------------------------------
# POST /api/tasks — 创建任务 + 触发分解
# ---------------------------------------------------------------------------

class TestCreateTask:
    @pytest.fixture(autouse=True)
    def _override_llm(self, mock_llm: MockLLMClient):
        """Inject MockLLMClient into the tasks router for every test."""
        app.dependency_overrides[get_llm_client] = lambda: mock_llm
        yield
        app.dependency_overrides.pop(get_llm_client, None)

    async def test_create_task_success(self, client: AsyncClient, mock_llm: MockLLMClient):
        resp = await client.post("/api/tasks", json=VALID_PAYLOAD)
        assert resp.status_code == 201
        data = resp.json()

        # Task fields
        assert data["title"] == VALID_PAYLOAD["title"]
        assert data["mode"] == "report"
        assert data["depth"] == "standard"
        assert data["target_words"] == 10000
        assert data["status"] == "pending"
        assert data["fsm_state"] == "init"

        # DAG nodes created from mock response (3 nodes)
        assert len(data["nodes"]) == 3
        roles = {n["agent_role"] for n in data["nodes"]}
        assert "outline" in roles
        assert "writer" in roles

        # LLM was called with orchestrator role
        assert any(c["role"] == "orchestrator" for c in mock_llm.call_log)

    async def test_create_task_with_novel_mode(self, client: AsyncClient):
        payload = {**VALID_PAYLOAD, "mode": "novel", "target_words": 50000}
        resp = await client.post("/api/tasks", json=payload)
        assert resp.status_code == 201
        assert resp.json()["mode"] == "novel"

    async def test_create_task_title_too_short(self, client: AsyncClient):
        payload = {**VALID_PAYLOAD, "title": "短"}
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
        payload = {"title": "默认值测试任务标题足够长"}
        resp = await client.post("/api/tasks", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["mode"] == "report"
        assert data["depth"] == "standard"
        assert data["target_words"] == 10000

    async def test_create_task_nodes_have_correct_dependencies(
        self, client: AsyncClient
    ):
        resp = await client.post("/api/tasks", json=VALID_PAYLOAD)
        assert resp.status_code == 201
        nodes = resp.json()["nodes"]
        # First node (outline) has no dependencies
        outline_node = next(n for n in nodes if n["agent_role"] == "outline")
        assert outline_node["depends_on"] is None or outline_node["depends_on"] == []
        # Writer nodes depend on outline
        writer_nodes = [n for n in nodes if n["agent_role"] == "writer"]
        for wn in writer_nodes:
            assert wn["depends_on"] is not None
            assert len(wn["depends_on"]) > 0


# ---------------------------------------------------------------------------
# GET /api/tasks/{id} — 获取任务详情
# ---------------------------------------------------------------------------

class TestGetTask:
    @pytest.fixture(autouse=True)
    def _override_llm(self, mock_llm: MockLLMClient):
        app.dependency_overrides[get_llm_client] = lambda: mock_llm
        yield
        app.dependency_overrides.pop(get_llm_client, None)

    async def test_get_task_success(self, client: AsyncClient):
        # Create first
        create_resp = await client.post("/api/tasks", json=VALID_PAYLOAD)
        task_id = create_resp.json()["id"]

        # Get detail
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


# ---------------------------------------------------------------------------
# GET /api/tasks — 历史任务列表
# ---------------------------------------------------------------------------

class TestListTasks:
    @pytest.fixture(autouse=True)
    def _override_llm(self, mock_llm: MockLLMClient):
        app.dependency_overrides[get_llm_client] = lambda: mock_llm
        yield
        app.dependency_overrides.pop(get_llm_client, None)

    async def test_list_tasks_empty(self, client: AsyncClient):
        resp = await client.get("/api/tasks")
        assert resp.status_code == 200
        # May contain tasks from other tests, just check it's a list
        assert isinstance(resp.json(), list)

    async def test_list_tasks_after_create(self, client: AsyncClient):
        # Note: other tests may also have created tasks in the same DB
        # So we create one and verify it appears in the list
        create_resp = await client.post("/api/tasks", json=VALID_PAYLOAD)
        created_id = create_resp.json()["id"]

        resp = await client.get("/api/tasks")
        assert resp.status_code == 200
        ids = [t["id"] for t in resp.json()]
        assert created_id in ids

    async def test_list_tasks_no_nodes_field(self, client: AsyncClient):
        """List endpoint returns TaskRead (no nodes), not TaskDetailRead."""
        await client.post("/api/tasks", json=VALID_PAYLOAD)
        resp = await client.get("/api/tasks")
        assert resp.status_code == 200
        for t in resp.json():
            assert "nodes" not in t

    async def test_list_tasks_ordered_newest_first(self, client: AsyncClient):
        """Tasks should be ordered by created_at descending."""
        r1 = await client.post(
            "/api/tasks",
            json={**VALID_PAYLOAD, "title": "第一个任务测试标题"},
        )
        r2 = await client.post(
            "/api/tasks",
            json={**VALID_PAYLOAD, "title": "第二个任务测试标题"},
        )
        id1 = r1.json()["id"]
        id2 = r2.json()["id"]

        resp = await client.get("/api/tasks")
        ids = [t["id"] for t in resp.json()]
        # Second created task should appear before first
        assert ids.index(id2) < ids.index(id1)
