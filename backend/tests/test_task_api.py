"""Tests for Task API - Step 2.3"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.agent import Agent
from app.main import app
from app.models.task import Task
from app.models.task_node import TaskNode
from app.routers.tasks import get_llm_client
from app.services.task_service import persist_monitor_recovery_event
from tests.conftest import MockLLMClient


VALID_PAYLOAD = {
    "title": "Quantum computing report generation task",
    "mode": "report",
    "depth": "standard",
    "target_words": 10000,
}
AUTH_HEADERS = {"Authorization": "Bearer token-user"}


async def _create_task_detail(client: AsyncClient) -> dict:
    resp = await client.post("/api/tasks", json=VALID_PAYLOAD, headers=AUTH_HEADERS)
    assert resp.status_code == 201
    return resp.json()


async def _set_task_status(session: AsyncSession, task_id: str, status: str) -> None:
    await session.execute(
        update(Task)
        .where(Task.id == uuid.UUID(task_id))
        .values(status=status)
    )
    await session.commit()


async def _set_control_status(session: AsyncSession, task_id: str, control_status: str) -> None:
    task = await session.get(Task, uuid.UUID(task_id))
    assert task is not None
    checkpoint = dict(task.checkpoint_data or {})
    control = dict(checkpoint.get("control") or {})
    control["status"] = control_status
    checkpoint["control"] = control
    await session.execute(
        update(Task)
        .where(Task.id == uuid.UUID(task_id))
        .values(checkpoint_data=checkpoint)
    )
    await session.commit()


async def _set_node_status(session: AsyncSession, node_id: str, status: str) -> None:
    await session.execute(
        update(TaskNode)
        .where(TaskNode.id == uuid.UUID(node_id))
        .values(status=status)
    )
    await session.commit()


async def _set_node_retry_count(session: AsyncSession, node_id: str, retry_count: int) -> None:
    await session.execute(
        update(TaskNode)
        .where(TaskNode.id == uuid.UUID(node_id))
        .values(retry_count=retry_count)
    )
    await session.commit()


def _assert_control_response(detail: dict, resp: AsyncClient | None, expected_status: str | None = None) -> dict:
    assert resp is not None
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == detail["id"]
    checkpoint = data.get("checkpoint_data", {})
    control = checkpoint.get("control")
    assert control is not None
    assert control.get("status") is not None
    if expected_status is not None:
        assert control["status"] == expected_status
    return data


def _find_node(nodes: list[dict], node_id: str) -> dict:
    return next(node for node in nodes if node["id"] == node_id)


class TestCreateTask:
    @pytest.fixture(autouse=True)
    def _override_llm(self, mock_llm: MockLLMClient):
        app.dependency_overrides[get_llm_client] = lambda: mock_llm
        yield
        app.dependency_overrides.pop(get_llm_client, None)

    async def test_create_task_success(self, client: AsyncClient, mock_llm: MockLLMClient):
        resp = await client.post("/api/tasks", json=VALID_PAYLOAD, headers=AUTH_HEADERS)
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
        resp = await client.post("/api/tasks", json=payload, headers=AUTH_HEADERS)
        assert resp.status_code == 201
        assert resp.json()["mode"] == "novel"

    async def test_create_task_title_too_short(self, client: AsyncClient):
        payload = {**VALID_PAYLOAD, "title": "short"}
        resp = await client.post("/api/tasks", json=payload, headers=AUTH_HEADERS)
        assert resp.status_code == 422

    async def test_create_task_invalid_mode(self, client: AsyncClient):
        payload = {**VALID_PAYLOAD, "mode": "invalid"}
        resp = await client.post("/api/tasks", json=payload, headers=AUTH_HEADERS)
        assert resp.status_code == 422

    async def test_create_task_invalid_depth(self, client: AsyncClient):
        payload = {**VALID_PAYLOAD, "depth": "ultra_deep"}
        resp = await client.post("/api/tasks", json=payload, headers=AUTH_HEADERS)
        assert resp.status_code == 422

    async def test_create_task_target_words_too_low(self, client: AsyncClient):
        payload = {**VALID_PAYLOAD, "target_words": 100}
        resp = await client.post("/api/tasks", json=payload, headers=AUTH_HEADERS)
        assert resp.status_code == 422

    async def test_create_task_target_words_too_high(self, client: AsyncClient):
        payload = {**VALID_PAYLOAD, "target_words": 300000}
        resp = await client.post("/api/tasks", json=payload, headers=AUTH_HEADERS)
        assert resp.status_code == 422

    async def test_create_task_default_values(self, client: AsyncClient):
        payload = {"title": "Default value task title long enough"}
        resp = await client.post("/api/tasks", json=payload, headers=AUTH_HEADERS)
        assert resp.status_code == 201
        data = resp.json()
        assert data["mode"] == "report"
        assert data["depth"] == "standard"
        assert data["target_words"] == 10000

    async def test_create_task_with_draft_text_enters_pre_review_integrity(
        self, client: AsyncClient
    ):
        payload = {**VALID_PAYLOAD, "draft_text": "Existing draft content"}
        resp = await client.post("/api/tasks", json=payload, headers=AUTH_HEADERS)
        assert resp.status_code == 201
        assert resp.json()["fsm_state"] == "pre_review_integrity"

    async def test_create_task_with_review_comments_enters_pre_review_integrity(
        self, client: AsyncClient
    ):
        payload = {
            **VALID_PAYLOAD,
            "review_comments": "Please fix unsupported claims.",
        }
        resp = await client.post("/api/tasks", json=payload, headers=AUTH_HEADERS)
        assert resp.status_code == 201
        assert resp.json()["fsm_state"] == "pre_review_integrity"

    async def test_create_task_nodes_have_correct_dependencies(self, client: AsyncClient):
        resp = await client.post("/api/tasks", json=VALID_PAYLOAD, headers=AUTH_HEADERS)
        assert resp.status_code == 201
        nodes = resp.json()["nodes"]

        outline_node = next(n for n in nodes if n["agent_role"] == "outline")
        assert outline_node["depends_on"] is None or outline_node["depends_on"] == []

        writer_nodes = [n for n in nodes if n["agent_role"] == "writer"]
        for wn in writer_nodes:
            assert wn["depends_on"] is not None
            assert len(wn["depends_on"]) > 0


class TestCreateTaskWithRuntimeLlmSelection:
    async def test_create_task_uses_debug_mock_llm_when_enabled(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        app.dependency_overrides.pop(get_llm_client, None)
        get_llm_client.cache_clear()
        monkeypatch.setattr(settings, "mock_llm_enabled", True)
        monkeypatch.setattr(settings, "openai_api_key", "sk-xxx")
        monkeypatch.setattr(settings, "deepseek_api_key", "sk-xxx")

        resp = await client.post("/api/tasks", json=VALID_PAYLOAD, headers=AUTH_HEADERS)

        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert len(data["nodes"]) == 3

        get_llm_client.cache_clear()

    async def test_create_task_returns_503_when_llm_unavailable_without_mock_mode(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        app.dependency_overrides.pop(get_llm_client, None)
        get_llm_client.cache_clear()
        monkeypatch.setattr(settings, "mock_llm_enabled", False)
        monkeypatch.setattr(settings, "openai_api_key", "sk-xxx")
        monkeypatch.setattr(settings, "deepseek_api_key", "sk-xxx")

        resp = await client.post("/api/tasks", json=VALID_PAYLOAD, headers=AUTH_HEADERS)

        assert resp.status_code == 503
        assert "LLM service unavailable" in resp.json()["detail"]

        get_llm_client.cache_clear()


class TestGetTask:
    @pytest.fixture(autouse=True)
    def _override_llm(self, mock_llm: MockLLMClient):
        app.dependency_overrides[get_llm_client] = lambda: mock_llm
        yield
        app.dependency_overrides.pop(get_llm_client, None)

    async def test_get_task_success(self, client: AsyncClient):
        create_resp = await client.post("/api/tasks", json=VALID_PAYLOAD, headers=AUTH_HEADERS)
        task_id = create_resp.json()["id"]

        resp = await client.get(f"/api/tasks/{task_id}", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == task_id
        assert data["title"] == VALID_PAYLOAD["title"]
        assert len(data["nodes"]) == 3

    async def test_get_task_includes_monitor_recovery_snapshot_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        detail = await _create_task_detail(client)
        node_id = detail["nodes"][0]["id"]
        agent = Agent(name="monitor-agent", role="writer", layer=1)
        db_session.add(agent)
        await db_session.flush()
        assigned_agent_id = agent.id
        started_at = datetime.now(UTC).replace(tzinfo=None)
        finished_at = datetime.now(UTC).replace(tzinfo=None)

        await db_session.execute(
            update(TaskNode)
            .where(TaskNode.id == uuid.UUID(node_id))
            .values(
                assigned_agent=assigned_agent_id,
                started_at=started_at,
                finished_at=finished_at,
            )
        )
        await db_session.execute(
            update(Task)
            .where(Task.id == uuid.UUID(detail["id"]))
            .values(
                checkpoint_data={
                    "control": {
                        "status": "active",
                        "preview_cache": {node_id: {"content": "preview body"}},
                        "review_scores": {node_id: {"score": 91}},
                    }
                }
            )
        )
        await db_session.commit()

        resp = await client.get(f"/api/tasks/{detail['id']}", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        node = _find_node(data["nodes"], node_id)

        assert node["assigned_agent"] == str(assigned_agent_id)
        assert node["started_at"] is not None
        assert node["finished_at"] is not None
        assert data["checkpoint_data"]["control"]["status"] == "active"
        assert data["checkpoint_data"]["control"]["preview_cache"][node_id]["content"] == "preview body"
        assert data["checkpoint_data"]["control"]["review_scores"][node_id]["score"] == 91

    async def test_get_task_not_found(self, client: AsyncClient):
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/tasks/{fake_id}", headers=AUTH_HEADERS)
        assert resp.status_code == 404

    async def test_get_task_invalid_uuid(self, client: AsyncClient):
        resp = await client.get("/api/tasks/not-a-uuid", headers=AUTH_HEADERS)
        assert resp.status_code == 422

    async def test_get_task_for_other_user_returns_404(
        self, client: AsyncClient
    ):
        create_resp = await client.post("/api/tasks", json=VALID_PAYLOAD, headers=AUTH_HEADERS)
        task_id = create_resp.json()["id"]

        old_tokens = settings.task_auth_tokens
        old_admins = settings.admin_user_ids
        settings.task_auth_tokens = f"{old_tokens},token-other:other-user"
        settings.admin_user_ids = old_admins
        try:
            resp = await client.get(
                f"/api/tasks/{task_id}",
                headers={"Authorization": "Bearer token-other"},
            )
        finally:
            settings.task_auth_tokens = old_tokens
            settings.admin_user_ids = old_admins
        assert resp.status_code == 404


class TestListTasks:
    @pytest.fixture(autouse=True)
    def _override_llm(self, mock_llm: MockLLMClient):
        app.dependency_overrides[get_llm_client] = lambda: mock_llm
        yield
        app.dependency_overrides.pop(get_llm_client, None)

    async def test_list_tasks_empty(self, client: AsyncClient):
        resp = await client.get("/api/tasks", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body and "total" in body
        assert isinstance(body["items"], list)

    async def test_list_tasks_after_create(self, client: AsyncClient):
        create_resp = await client.post("/api/tasks", json=VALID_PAYLOAD, headers=AUTH_HEADERS)
        created_id = create_resp.json()["id"]

        resp = await client.get("/api/tasks", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        ids = [t["id"] for t in resp.json()["items"]]
        assert created_id in ids

    async def test_list_tasks_no_nodes_field(self, client: AsyncClient):
        await client.post("/api/tasks", json=VALID_PAYLOAD, headers=AUTH_HEADERS)
        resp = await client.get("/api/tasks", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        for t in resp.json()["items"]:
            assert "nodes" not in t

    async def test_list_tasks_ordered_newest_first(self, client: AsyncClient):
        r1 = await client.post(
            "/api/tasks",
            json={**VALID_PAYLOAD, "title": "First task ordering check"},
            headers=AUTH_HEADERS,
        )
        r2 = await client.post(
            "/api/tasks",
            json={**VALID_PAYLOAD, "title": "Second task ordering check"},
            headers=AUTH_HEADERS,
        )
        id1 = r1.json()["id"]
        id2 = r2.json()["id"]

        resp = await client.get("/api/tasks", headers=AUTH_HEADERS)
        ids = [t["id"] for t in resp.json()["items"]]
        assert ids.index(id2) < ids.index(id1)


CONTROL_VISIBILITY_CASES: list[tuple[str, Callable[[dict], dict | None]]] = [
    ("pause", lambda _: None),
    ("resume", lambda _: None),
    ("skip", lambda detail: {"node_id": detail["nodes"][0]["id"]}),
    ("retry", lambda detail: {"node_id": detail["nodes"][0]["id"]}),
]


class TestTaskControlAPI:
    @pytest.fixture(autouse=True)
    def _override_llm(self, mock_llm: MockLLMClient):
        app.dependency_overrides[get_llm_client] = lambda: mock_llm
        yield
        app.dependency_overrides.pop(get_llm_client, None)

    async def test_pause_endpoint_happy_path(self, client: AsyncClient):
        detail = await _create_task_detail(client)
        resp = await client.post(
            f"/api/tasks/{detail['id']}/control/pause",
            headers=AUTH_HEADERS,
        )
        data = _assert_control_response(detail, resp, expected_status="pause_requested")
        assert data["checkpoint_data"]["control"]["status"] == "pause_requested"

    async def test_pause_endpoint_duplicate_request_returns_409(self, client: AsyncClient):
        detail = await _create_task_detail(client)
        first = await client.post(
            f"/api/tasks/{detail['id']}/control/pause",
            headers=AUTH_HEADERS,
        )
        assert first.status_code == 200

        second = await client.post(
            f"/api/tasks/{detail['id']}/control/pause",
            headers=AUTH_HEADERS,
        )
        assert second.status_code == 409

    async def test_pause_endpoint_terminal_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        detail = await _create_task_detail(client)
        await _set_task_status(db_session, detail['id'], 'done')
        resp = await client.post(
            f"/api/tasks/{detail['id']}/control/pause",
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 409

    async def test_resume_endpoint_happy_path(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        detail = await _create_task_detail(client)
        await _set_control_status(db_session, detail['id'], 'paused')
        resp = await client.post(
            f"/api/tasks/{detail['id']}/control/resume",
            headers=AUTH_HEADERS,
        )
        data = _assert_control_response(detail, resp, expected_status="active")
        assert data["checkpoint_data"]["control"]["status"] == "active"

    async def test_resume_endpoint_illegal_state_returns_409(self, client: AsyncClient):
        detail = await _create_task_detail(client)
        resp = await client.post(
            f"/api/tasks/{detail['id']}/control/resume",
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 409

    async def test_resume_terminal_task_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        detail = await _create_task_detail(client)
        await _set_control_status(db_session, detail['id'], 'paused')
        await _set_task_status(db_session, detail['id'], 'done')

        resp = await client.post(
            f"/api/tasks/{detail['id']}/control/resume",
            headers=AUTH_HEADERS,
        )

        assert resp.status_code == 409

    async def test_skip_endpoint_happy_path(self, client: AsyncClient):
        detail = await _create_task_detail(client)
        node_id = detail['nodes'][0]['id']
        resp = await client.post(
            f"/api/tasks/{detail['id']}/control/skip",
            json={"node_id": node_id},
            headers=AUTH_HEADERS,
        )
        data = _assert_control_response(detail, resp)
        node = _find_node(data["nodes"], node_id)
        assert node["status"] == "skipped"

    async def test_skip_missing_node_id_returns_422(self, client: AsyncClient):
        detail = await _create_task_detail(client)
        resp = await client.post(
            f"/api/tasks/{detail['id']}/control/skip",
            json={},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 422

    async def test_skip_illegal_state_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        detail = await _create_task_detail(client)
        node_id = detail['nodes'][0]['id']
        await _set_node_status(db_session, node_id, 'done')
        resp = await client.post(
            f"/api/tasks/{detail['id']}/control/skip",
            json={"node_id": node_id},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 409

    async def test_skip_terminal_task_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        detail = await _create_task_detail(client)
        node_id = detail['nodes'][0]['id']
        await _set_task_status(db_session, detail['id'], 'failed')

        resp = await client.post(
            f"/api/tasks/{detail['id']}/control/skip",
            json={"node_id": node_id},
            headers=AUTH_HEADERS,
        )

        assert resp.status_code == 409

    async def test_retry_endpoint_happy_path(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        detail = await _create_task_detail(client)
        node_id = detail['nodes'][0]['id']
        await _set_node_status(db_session, node_id, 'failed')
        resp = await client.post(
            f"/api/tasks/{detail['id']}/control/retry",
            json={"node_id": node_id},
            headers=AUTH_HEADERS,
        )
        data = _assert_control_response(detail, resp)
        node = _find_node(data["nodes"], node_id)
        assert node["status"] == "ready"

    async def test_retry_endpoint_resets_manual_retry_budget(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        detail = await _create_task_detail(client)
        node_id = detail['nodes'][0]['id']
        await _set_node_status(db_session, node_id, 'failed')
        await _set_node_retry_count(db_session, node_id, 3)

        resp = await client.post(
            f"/api/tasks/{detail['id']}/control/retry",
            json={"node_id": node_id},
            headers=AUTH_HEADERS,
        )

        data = _assert_control_response(detail, resp)
        node = _find_node(data["nodes"], node_id)
        assert node["status"] == "ready"
        assert node["retry_count"] == 0

    async def test_retry_missing_node_id_returns_422(self, client: AsyncClient):
        detail = await _create_task_detail(client)
        resp = await client.post(
            f"/api/tasks/{detail['id']}/control/retry",
            json={},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 422

    async def test_retry_illegal_state_returns_409(self, client: AsyncClient):
        detail = await _create_task_detail(client)
        node_id = detail['nodes'][0]['id']
        resp = await client.post(
            f"/api/tasks/{detail['id']}/control/retry",
            json={"node_id": node_id},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 409

    async def test_retry_terminal_task_returns_409(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        detail = await _create_task_detail(client)
        node_id = detail['nodes'][0]['id']
        await _set_task_status(db_session, detail['id'], 'failed')
        await _set_node_status(db_session, node_id, 'failed')

        resp = await client.post(
            f"/api/tasks/{detail['id']}/control/retry",
            json={"node_id": node_id},
            headers=AUTH_HEADERS,
        )

        assert resp.status_code == 409

    @pytest.mark.parametrize("suffix, body_factory", CONTROL_VISIBILITY_CASES)
    async def test_control_endpoint_requires_visible_task(
        self,
        client: AsyncClient,
        suffix: str,
        body_factory: Callable[[dict], dict | None],
    ):
        detail = await _create_task_detail(client)
        old_tokens = settings.task_auth_tokens
        old_admins = settings.admin_user_ids
        settings.task_auth_tokens = f"{old_tokens},token-other:other-user"
        body = body_factory(detail)
        request_kwargs = {"headers": {"Authorization": "Bearer token-other"}}
        if body is not None:
            request_kwargs["json"] = body
        try:
            resp = await client.post(
                f"/api/tasks/{detail['id']}/control/{suffix}",
                **request_kwargs,
            )
            assert resp.status_code == 404
        finally:
            settings.task_auth_tokens = old_tokens
            settings.admin_user_ids = old_admins


class TestTaskRecoveryPersistence:
    @pytest.fixture(autouse=True)
    def _override_llm(self, mock_llm: MockLLMClient):
        app.dependency_overrides[get_llm_client] = lambda: mock_llm
        yield
        app.dependency_overrides.pop(get_llm_client, None)

    async def test_persisted_chapter_preview_is_visible_in_fresh_get(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        detail = await _create_task_detail(client)
        node_id = detail["nodes"][0]["id"]

        await persist_monitor_recovery_event(
            task_id=detail["id"],
            node_id=node_id,
            event_type="chapter_preview",
            payload={"content": "chapter preview body", "chapter_index": 1},
            session=db_session,
        )
        await db_session.commit()

        resp = await client.get(f"/api/tasks/{detail['id']}", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        preview_cache = data["checkpoint_data"]["control"]["preview_cache"]
        assert preview_cache[node_id]["content"] == "chapter preview body"
        assert preview_cache[node_id]["chapter_index"] == 1

    async def test_persisted_review_score_is_visible_in_fresh_get(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        detail = await _create_task_detail(client)
        node_id = detail["nodes"][0]["id"]

        await persist_monitor_recovery_event(
            task_id=detail["id"],
            node_id=node_id,
            event_type="review_score",
            payload={"score": 88, "feedback": "solid"},
            session=db_session,
        )
        await db_session.commit()

        resp = await client.get(f"/api/tasks/{detail['id']}", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        review_scores = data["checkpoint_data"]["control"]["review_scores"]
        assert review_scores[node_id]["score"] == 88
        assert review_scores[node_id]["feedback"] == "solid"
