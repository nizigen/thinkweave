"""Tests for Agent CRUD API."""

import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.config import settings
from app.services import agent_manager

AUTH_TOKEN = "token-admin"
AUTH_USER = "admin-user"
AUTH_HEADERS = {"Authorization": f"Bearer {AUTH_TOKEN}"}

VALID_AGENT = {
    "name": "test_writer",
    "role": "writer",
    "layer": 2,
    "capabilities": "content generation",
    "model": "deepseek-v3.2",
    "agent_config": {
        "goal": "Write high-quality chapters with low overlap",
        "backstory": "Long-form technical writer",
        "temperature": 0.4,
        "max_tokens": 4000,
        "max_retries": 3,
        "max_tool_iterations": 2,
        "fallback_models": ["gpt-5.2", "deepseek-v3.2"],
        "tool_allowlist": ["web_search", "vector_retrieve"],
    },
}


@pytest.fixture(autouse=True)
def mock_runtime_registry(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    register = AsyncMock()
    unregister = AsyncMock()
    monkeypatch.setattr(agent_manager, "register_persisted_agent", register)
    monkeypatch.setattr(agent_manager, "unregister_runtime_agent", unregister)
    return {
        "register": register,
        "unregister": unregister,
    }


class TestCreateAgent:
    async def test_create_success(
        self,
        client: AsyncClient,
        mock_runtime_registry: dict[str, AsyncMock],
    ):
        resp = await client.post("/api/agents", json=VALID_AGENT, headers=AUTH_HEADERS)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test_writer"
        assert data["role"] == "writer"
        assert data["layer"] == 2
        assert data["status"] == "idle"
        assert data["agent_config"]["goal"] == VALID_AGENT["agent_config"]["goal"]
        mock_runtime_registry["register"].assert_awaited_once()

    async def test_create_persists_offline_when_runtime_registration_fails(
        self,
        client: AsyncClient,
        mock_runtime_registry: dict[str, AsyncMock],
    ):
        mock_runtime_registry["register"].side_effect = RuntimeError("runtime down")

        resp = await client.post("/api/agents", json=VALID_AGENT, headers=AUTH_HEADERS)

        assert resp.status_code == 201
        assert resp.json()["status"] == "offline"

    async def test_create_minimal_fields(self, client: AsyncClient):
        resp = await client.post(
            "/api/agents",
            json={"name": "minimal_agent", "role": "orchestrator", "layer": 0},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["model"] == settings.default_model
        assert data["capabilities"] is None
        assert data["agent_config"] is None

    async def test_create_normalizes_capabilities(self, client: AsyncClient):
        resp = await client.post(
            "/api/agents",
            json={
                "name": "cap-normalize",
                "role": "writer",
                "layer": 2,
                "capabilities": " Draft , retrieval;DRAFT | tooling ",
            },
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["capabilities"] == "draft, retrieval, tooling"

    async def test_create_supports_custom_model_choice(self, client: AsyncClient):
        resp = await client.post(
            "/api/agents",
            json={
                "name": "custom-model-agent",
                "role": "writer",
                "layer": 2,
                "model": "",
                "custom_model": "openrouter/anthropic/claude-sonnet-4",
            },
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["model"] == "openrouter/anthropic/claude-sonnet-4"

    async def test_create_writer_applies_role_preset_when_config_missing(
        self,
        client: AsyncClient,
    ):
        resp = await client.post(
            "/api/agents",
            json={"name": "writer-defaults", "role": "writer", "layer": 2},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["agent_config"] is not None
        assert data["agent_config"]["max_tool_iterations"] == 3
        assert "writer_evidence_first_policy" in data["agent_config"]["skill_allowlist"]
        assert "tavily_search" in data["agent_config"]["tool_allowlist"]
        assert "search_code" in data["agent_config"]["tool_allowlist"]

    async def test_create_preserves_user_provided_agent_config(
        self,
        client: AsyncClient,
    ):
        resp = await client.post(
            "/api/agents",
            json={
                "name": "writer-custom-config",
                "role": "writer",
                "layer": 2,
                "agent_config": {
                    "max_tool_iterations": 1,
                    "skill_allowlist": ["technical_report"],
                    "tool_allowlist": ["search_files"],
                },
            },
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["agent_config"]["max_tool_iterations"] == 1
        assert data["agent_config"]["skill_allowlist"] == ["technical_report"]
        assert data["agent_config"]["tool_allowlist"] == ["search_files"]

    async def test_create_missing_required_field(self, client: AsyncClient):
        resp = await client.post(
            "/api/agents", json={"name": "incomplete"}, headers=AUTH_HEADERS
        )
        assert resp.status_code == 422

    async def test_create_rejects_oversized_capability_token(self, client: AsyncClient):
        long_token = "x" * 65
        resp = await client.post(
            "/api/agents",
            json={
                "name": "bad-cap",
                "role": "writer",
                "layer": 2,
                "capabilities": long_token,
            },
            headers=AUTH_HEADERS,
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

    async def test_model_options_available(self, client: AsyncClient):
        resp = await client.get("/api/agents/model-options", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(item["value"] == settings.default_model for item in data)

    async def test_skill_options_available(self, client: AsyncClient):
        resp = await client.get("/api/agents/skills", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_role_presets_available(self, client: AsyncClient):
        resp = await client.get("/api/agents/role-presets", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        writer = next(item for item in data if item["role"] == "writer")
        assert writer["layer"] == 2
        assert "writer_evidence_first_policy" in writer["agent_config"]["skill_allowlist"]

    async def test_tool_options_available(self, client: AsyncClient):
        resp = await client.get("/api/agents/tool-options", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


class TestUpdateDelete:
    async def test_update_and_delete(
        self,
        client: AsyncClient,
        mock_runtime_registry: dict[str, AsyncMock],
    ):
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
        mock_runtime_registry["unregister"].assert_awaited_once_with(uuid.UUID(agent_id))


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
