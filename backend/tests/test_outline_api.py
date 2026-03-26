"""Step 6.4 大纲 API 测试"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

AUTH = {"Authorization": "Bearer token-user"}


@pytest.mark.asyncio
class TestOutlineAPI:
    async def test_get_outline_not_found(self, client: AsyncClient):
        """不存在的任务返回 404"""
        resp = await client.get(f"/api/tasks/{uuid.uuid4()}/outline", headers=AUTH)
        assert resp.status_code == 404

    async def test_get_outline_endpoint_exists(self, client: AsyncClient):
        """GET /api/tasks/{id}/outline 端点存在（不返回 405）"""
        resp = await client.get(f"/api/tasks/{uuid.uuid4()}/outline", headers=AUTH)
        assert resp.status_code != 405

    async def test_confirm_outline_not_found(self, client: AsyncClient):
        """不存在的任务 confirm 返回 404"""
        resp = await client.post(
            f"/api/tasks/{uuid.uuid4()}/outline/confirm",
            json={"content": "# 大纲\n## 第一章"},
            headers=AUTH,
        )
        assert resp.status_code == 404

    async def test_confirm_outline_endpoint_exists(self, client: AsyncClient):
        """POST /api/tasks/{id}/outline/confirm 不返回 405"""
        resp = await client.post(
            f"/api/tasks/{uuid.uuid4()}/outline/confirm",
            json={"content": "# 大纲\n## 第一章"},
            headers=AUTH,
        )
        assert resp.status_code != 405

    async def test_confirm_outline_requires_content(self, client: AsyncClient):
        """POST outline/confirm 缺少 content 返回 422"""
        resp = await client.post(
            f"/api/tasks/{uuid.uuid4()}/outline/confirm",
            json={},
            headers=AUTH,
        )
        assert resp.status_code == 422

    async def test_outline_read_schema(self, client: AsyncClient):
        """OutlineRead schema 包含必要字段"""
        from app.routers.outline import OutlineRead
        import inspect
        fields = OutlineRead.model_fields
        for f in ["id", "task_id", "content", "version", "confirmed"]:
            assert f in fields
