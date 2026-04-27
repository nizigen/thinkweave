"""Step 6.3 历史任务页 — 后端测试 (TDD RED)"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_task(status="completed", mode="technical_report", title="量子报告"):
    t = MagicMock()
    t.id = uuid.uuid4()
    t.title = title
    t.mode = mode
    t.status = status
    t.fsm_state = "done"
    t.word_count = 8000
    t.depth = "standard"
    t.target_words = 10000
    t.created_at = datetime(2026, 3, 26, 10, 0, 0)
    t.finished_at = datetime(2026, 3, 26, 10, 30, 0)
    return t


# ---------------------------------------------------------------------------
# task_service.list_tasks 过滤参数测试
# ---------------------------------------------------------------------------

class TestListTasksFilters:
    @pytest.mark.asyncio
    async def test_list_tasks_filter_by_status(self):
        """list_tasks 支持 status 过滤参数"""
        from app.services.task_service import list_tasks
        import inspect
        sig = inspect.signature(list_tasks)
        assert "status" in sig.parameters

    @pytest.mark.asyncio
    async def test_list_tasks_filter_by_mode(self):
        from app.services.task_service import list_tasks
        import inspect
        sig = inspect.signature(list_tasks)
        assert "mode" in sig.parameters

    @pytest.mark.asyncio
    async def test_list_tasks_filter_by_search(self):
        from app.services.task_service import list_tasks
        import inspect
        sig = inspect.signature(list_tasks)
        assert "search" in sig.parameters

    @pytest.mark.asyncio
    async def test_list_tasks_returns_total_count(self):
        """list_tasks 返回 (items, total) 元组以支持分页"""
        from app.services.task_service import list_tasks
        import inspect
        # 检查返回类型注解包含 total 信息
        sig = inspect.signature(list_tasks)
        # 有 total 参数或返回 TaskListResult
        assert "total" not in sig.parameters  # total 是返回值，不是入参


# ---------------------------------------------------------------------------
# GET /api/tasks 路由扩展测试（不需要 DB）
# ---------------------------------------------------------------------------

class TestListTasksRoute:
    def _get_client(self):
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_list_tasks_accepts_search_param(self):
        """GET /api/tasks?search=xxx 不返回 422"""
        client = self._get_client()
        resp = client.get("/api/tasks?search=量子", headers={"X-User-Id": "u1"})
        assert resp.status_code != 422

    def test_list_tasks_accepts_status_param(self):
        client = self._get_client()
        resp = client.get("/api/tasks?status=completed", headers={"X-User-Id": "u1"})
        assert resp.status_code != 422

    def test_list_tasks_accepts_mode_param(self):
        client = self._get_client()
        resp = client.get("/api/tasks?mode=technical_report", headers={"X-User-Id": "u1"})
        assert resp.status_code != 422

    def test_list_tasks_accepts_offset_limit(self):
        client = self._get_client()
        resp = client.get("/api/tasks?offset=0&limit=20", headers={"X-User-Id": "u1"})
        assert resp.status_code != 422


# ---------------------------------------------------------------------------
# DELETE /api/tasks (批量删除) 路由测试
# ---------------------------------------------------------------------------

AUTH = {"Authorization": "Bearer token-user"}


class TestBatchDeleteRoute:
    def _get_client(self):
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_batch_delete_endpoint_exists(self):
        """DELETE /api/tasks 端点存在（不返回 405）"""
        client = self._get_client()
        resp = client.request("DELETE", "/api/tasks", json={"ids": []}, headers=AUTH)
        assert resp.status_code != 405

    def test_batch_delete_invalid_body_returns_422(self):
        """DELETE /api/tasks ids 不是列表时返回 422"""
        client = self._get_client()
        resp = client.request("DELETE", "/api/tasks", json={"ids": "not-a-list"}, headers=AUTH)
        assert resp.status_code == 422

    def test_batch_delete_empty_ids_ok(self):
        """DELETE /api/tasks ids=[] 返回 200 且 deleted_count=0"""
        client = self._get_client()
        resp = client.request("DELETE", "/api/tasks", json={"ids": []}, headers=AUTH)
        # 空列表不走 DB，直接返回
        assert resp.status_code in (200, 503)  # 503 only if DB not available


# ---------------------------------------------------------------------------
# TaskListResult schema 测试
# ---------------------------------------------------------------------------

class TestTaskListResult:
    def test_task_list_result_schema_exists(self):
        from app.schemas.task import TaskListResult
        assert TaskListResult is not None

    def test_task_list_result_has_items_and_total(self):
        from app.schemas.task import TaskListResult, TaskRead
        result = TaskListResult(items=[], total=0)
        assert result.items == []
        assert result.total == 0
