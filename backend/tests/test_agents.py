"""Tests for Agent CRUD API."""

import uuid

from httpx import AsyncClient

from app.config import settings

AUTH_TOKEN = "token-admin"
AUTH_USER = "admin-user"
AUTH_HEADERS = {"Authorization": f"Bearer {AUTH_TOKEN}"}

VALID_AGENT = {
    "name": "test_writer",
    "role": "writer",
    "layer": 2,
    "capabilities": "content generation",
    "model": "deepseek-chat",
    "agent_config": {
        "goal": "Write high-quality chapters with low overlap",
        "backstory": "Long-form technical writer",
        "temperature": 0.4,
        "max_tokens": 4000,
        "max_retries": 3,
        "max_tool_iterations": 2,
        "fallback_models": ["gpt-4o-mini", "deepseek-chat"],
        "tool_allowlist": ["web_search", "vector_retrieve"],
    },
}


class TestCreateAgent:
    async def test_create_success(self, client: AsyncClient):
        resp = await client.post("/api/agents", json=VALID_AGENT, headers=AUTH_HEADERS)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test_writer"
        assert data["role"] == "writer"
        assert data["layer"] == 2
        assert data["status"] == "idle"
        assert data["agent_config"]["goal"] == VALID_AGENT["agent_config"]["goal"]

    async def test_create_minimal_fields(self, client: AsyncClient):
        resp = await client.post(
            "/api/agents",
            json={"name": "minimal_agent", "role": "orchestrator", "layer": 0},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["model"] == "gpt-4o"
        assert data["capabilities"] is None
        assert data["agent_config"] is None

    async def test_create_missing_required_field(self, client: AsyncClient):
        resp = await client.post(
            "/api/agents", json={"name": "incomplete"}, headers=AUTH_HEADERS
        )
        assert resp.status_code == 422


class TestReadAgents:
    async def test_list_returns_list(self, client: AsyncClient):
        resp = await client.get("/api/agents", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_get_not_found(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/agents/{fake_id}", headers=AUTH_HEADERS)
        assert resp.status_code == 404


class TestUpdateDelete:
    async def test_update_and_delete(self, client: AsyncClient):
        create_resp = await client.post("/api/agents", json=VALID_AGENT, headers=AUTH_HEADERS)
        agent_id = create_resp.json()["id"]

        update_resp = await client.patch(
            f"/api/agents/{agent_id}/status",
            json={"status": "busy"},
            headers=AUTH_HEADERS,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["status"] == "busy"

        delete_resp = await client.delete(f"/api/agents/{agent_id}", headers=AUTH_HEADERS)
        assert delete_resp.status_code == 204


class TestAuthz:
    async def test_agents_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/agents")
        assert resp.status_code == 401

    async def test_agents_write_requires_admin(self, client: AsyncClient):
        old_tokens = settings.task_auth_tokens
        old_admins = settings.admin_user_ids
        settings.task_auth_tokens = "token-user:normal-user"
        settings.admin_user_ids = "admin-user"
        try:
            resp = await client.post(
                "/api/agents",
                json=VALID_AGENT,
                headers={"Authorization": "Bearer token-user"},
            )
        finally:
            settings.task_auth_tokens = old_tokens
            settings.admin_user_ids = old_admins
        assert resp.status_code == 403
