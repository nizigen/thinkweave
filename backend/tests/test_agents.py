"""Tests for Agent CRUD API — Step 1.1 (TDD)"""

import uuid

from httpx import AsyncClient


VALID_AGENT = {
    "name": "test_writer",
    "role": "writer",
    "layer": 2,
    "capabilities": "content generation",
    "model": "deepseek-chat",
}


class TestCreateAgent:
    """POST /api/agents"""

    async def test_create_success(self, client: AsyncClient):
        resp = await client.post("/api/agents", json=VALID_AGENT)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test_writer"
        assert data["role"] == "writer"
        assert data["layer"] == 2
        assert data["status"] == "idle"
        assert "id" in data
        assert "created_at" in data

    async def test_create_minimal_fields(self, client: AsyncClient):
        """Only required fields — defaults applied."""
        resp = await client.post("/api/agents", json={
            "name": "minimal_agent",
            "role": "orchestrator",
            "layer": 0,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["model"] == "gpt-4o"
        assert data["capabilities"] is None

    async def test_create_missing_required_field(self, client: AsyncClient):
        resp = await client.post("/api/agents", json={"name": "incomplete"})
        assert resp.status_code == 422


class TestListAgents:
    """GET /api/agents"""

    async def test_list_returns_list(self, client: AsyncClient):
        resp = await client.get("/api/agents")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_list_includes_created(self, client: AsyncClient):
        create_resp = await client.post("/api/agents", json=VALID_AGENT)
        created_id = create_resp.json()["id"]

        resp = await client.get("/api/agents")
        assert resp.status_code == 200
        ids = [a["id"] for a in resp.json()]
        assert created_id in ids


class TestGetAgent:
    """GET /api/agents/{id}"""

    async def test_get_existing(self, client: AsyncClient):
        create_resp = await client.post("/api/agents", json=VALID_AGENT)
        agent_id = create_resp.json()["id"]

        resp = await client.get(f"/api/agents/{agent_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == agent_id
        assert resp.json()["name"] == "test_writer"

    async def test_get_not_found(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/agents/{fake_id}")
        assert resp.status_code == 404


class TestUpdateAgentStatus:
    """PATCH /api/agents/{id}/status"""

    async def test_update_to_busy(self, client: AsyncClient):
        create_resp = await client.post("/api/agents", json=VALID_AGENT)
        agent_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/agents/{agent_id}/status",
            json={"status": "busy"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "busy"

    async def test_update_to_offline(self, client: AsyncClient):
        create_resp = await client.post("/api/agents", json=VALID_AGENT)
        agent_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/agents/{agent_id}/status",
            json={"status": "offline"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "offline"

    async def test_update_invalid_status(self, client: AsyncClient):
        create_resp = await client.post("/api/agents", json=VALID_AGENT)
        agent_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/agents/{agent_id}/status",
            json={"status": "nonexistent"},
        )
        assert resp.status_code == 422

    async def test_update_not_found(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        resp = await client.patch(
            f"/api/agents/{fake_id}/status",
            json={"status": "busy"},
        )
        assert resp.status_code == 404


class TestDeleteAgent:
    """DELETE /api/agents/{id}"""

    async def test_delete_existing(self, client: AsyncClient):
        create_resp = await client.post("/api/agents", json=VALID_AGENT)
        agent_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/agents/{agent_id}")
        assert resp.status_code == 204

        # Verify agent is gone
        get_resp = await client.get(f"/api/agents/{agent_id}")
        assert get_resp.status_code == 404

    async def test_delete_not_found(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        resp = await client.delete(f"/api/agents/{fake_id}")
        assert resp.status_code == 404
