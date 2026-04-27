"""Step 7.1 端到端流程测试 — 完整任务生命周期验证"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task, Outline
from app.models.task_node import TaskNode
from tests.conftest import MockLLMClient
from app.routers.tasks import get_llm_client
from app.main import app

AUTH = {"Authorization": "Bearer token-user"}

REPORT_PAYLOAD = {
    "title": "E2E Test: Quantum Computing Technical Report",
    "mode": "report",
    "depth": "standard",
    "target_words": 10000,
}

NOVEL_PAYLOAD = {
    "title": "E2E Test: The Chronicles of the Void",
    "mode": "novel",
    "depth": "quick",
    "target_words": 3000,
}

CUSTOM_PAYLOAD = {
    "title": "E2E Test: Custom Mode Generation",
    "mode": "custom",
    "depth": "quick",
    "target_words": 3000,
}

DRAFT_PAYLOAD = {
    "title": "E2E Test: Draft Continuation",
    "mode": "report",
    "depth": "quick",
    "target_words": 5000,
    "draft_text": "This is an existing draft that should be continued. " * 20,
}

LONGFORM_PAYLOAD = {
    "title": "E2E Test: Longform 30k Report",
    "mode": "report",
    "depth": "deep",
    "target_words": 30000,
}


async def _create_task(client: AsyncClient, payload: dict) -> dict:
    resp = await client.post("/api/tasks", json=payload, headers=AUTH)
    assert resp.status_code == 201, f"Task creation failed: {resp.text}"
    return resp.json()


async def _get_task(client: AsyncClient, task_id: str) -> dict:
    resp = await client.get(f"/api/tasks/{task_id}", headers=AUTH)
    assert resp.status_code == 200
    return resp.json()


async def _simulate_fsm_complete(
    session: AsyncSession,
    task_id: str,
    output_text: str,
    word_count: int = 8500,
) -> None:
    """直接设置任务为完成状态，模拟 FSM 运行完毕"""
    await session.execute(
        update(Task)
        .where(Task.id == uuid.UUID(task_id))
        .values(
            status="completed",
            fsm_state="done",
            output_text=output_text,
            word_count=word_count,
            finished_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    await session.commit()


async def _simulate_outline_ready(
    session: AsyncSession,
    task_id: str,
    content: str,
) -> None:
    """插入大纲记录并设置 fsm_state=outline_review"""
    outline = Outline(
        task_id=uuid.UUID(task_id),
        content=content,
        version=1,
        confirmed=False,
    )
    session.add(outline)
    await session.execute(
        update(Task)
        .where(Task.id == uuid.UUID(task_id))
        .values(fsm_state="outline_review", status="running")
    )
    await session.commit()


# ---------------------------------------------------------------------------
# E2E Flow 1: 技术报告完整流程
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestReportE2EFlow:
    @pytest.fixture(autouse=True)
    def _override_llm(self, mock_llm: MockLLMClient):
        app.dependency_overrides[get_llm_client] = lambda: mock_llm
        yield
        app.dependency_overrides.pop(get_llm_client, None)

    async def test_report_task_creation_returns_201(self, client: AsyncClient):
        """技术报告任务创建成功，返回 id 和初始状态"""
        task = await _create_task(client, REPORT_PAYLOAD)
        assert "id" in task
        assert task["mode"] == "report"
        assert task["status"] in ("pending", "running")
        assert task["target_words"] == 10000

    async def test_report_task_has_nodes_after_creation(self, client: AsyncClient):
        """任务创建后 DAG 节点被生成"""
        task = await _create_task(client, REPORT_PAYLOAD)
        resp = await client.get(f"/api/tasks/{task['id']}", headers=AUTH)
        detail = resp.json()
        assert "nodes" in detail
        assert len(detail["nodes"]) > 0
        assert "node_status_summary" in detail
        assert "stage_progress" in detail
        assert "evidence_summary" in detail
        assert "citation_summary" in detail
        first_node = detail["nodes"][0]
        assert "stage_code" in first_node
        assert "stage_name" in first_node

    async def test_report_task_visible_in_history(self, client: AsyncClient):
        """创建后任务出现在历史列表中"""
        task = await _create_task(client, REPORT_PAYLOAD)
        resp = await client.get("/api/tasks", headers=AUTH)
        data = resp.json()
        assert data["total"] >= 1
        ids = [t["id"] for t in data["items"]]
        assert task["id"] in ids

    async def test_report_task_can_be_completed(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """任务模拟完成后可查询到输出文本和字数"""
        task = await _create_task(client, REPORT_PAYLOAD)
        output = "# 量子计算技术报告\n\n" + "这是量子计算的核心内容。" * 400
        await _simulate_fsm_complete(db_session, task["id"], output, word_count=8500)
        detail = await _get_task(client, task["id"])
        assert detail["status"] == "completed"
        assert detail["word_count"] >= 8000
        assert detail["output_text"] is not None

    async def test_completed_report_exportable_docx(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """完成的任务可导出 DOCX"""
        task = await _create_task(client, REPORT_PAYLOAD)
        output = "# Quantum Computing\n\n" + "Content chapter. " * 200
        await _simulate_fsm_complete(db_session, task["id"], output)
        resp = await client.get(f"/api/export/{task['id']}/docx", headers=AUTH)
        assert resp.status_code == 200
        assert "wordprocessingml" in resp.headers["content-type"]

    async def test_completed_report_exportable_pdf(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """完成的任务可导出 PDF"""
        task = await _create_task(client, REPORT_PAYLOAD)
        output = "# Quantum Computing\n\n" + "Content chapter. " * 200
        await _simulate_fsm_complete(db_session, task["id"], output)
        resp = await client.get(f"/api/export/{task['id']}/pdf", headers=AUTH)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"

    async def test_longform_30k_task_detail_exposes_quality_summaries(
        self, client: AsyncClient
    ):
        task = await _create_task(client, LONGFORM_PAYLOAD)
        detail = await _get_task(client, task["id"])
        assert detail["target_words"] == 30000
        assert detail["depth"] == "deep"
        assert isinstance(detail.get("evidence_summary"), dict)
        assert isinstance(detail.get("citation_summary"), dict)
        assert "stage_progress" in detail


# ---------------------------------------------------------------------------
# E2E Flow 2: 大纲确认流程
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestOutlineConfirmFlow:
    @pytest.fixture(autouse=True)
    def _override_llm(self, mock_llm: MockLLMClient):
        app.dependency_overrides[get_llm_client] = lambda: mock_llm
        yield
        app.dependency_overrides.pop(get_llm_client, None)

    async def test_outline_review_state_exposes_outline(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """大纲就绪后可通过 API 获取"""
        task = await _create_task(client, REPORT_PAYLOAD)
        outline_content = "# 大纲\n## 第一章 概述\n## 第二章 核心技术\n## 第三章 总结"
        await _simulate_outline_ready(db_session, task["id"], outline_content)
        resp = await client.get(f"/api/tasks/{task['id']}/outline", headers=AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == outline_content
        assert data["confirmed"] is False

    async def test_outline_confirm_transitions_task(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """确认大纲后任务状态更新，大纲 confirmed=True"""
        task = await _create_task(client, REPORT_PAYLOAD)
        outline_content = "# 大纲\n## 第一章\n## 第二章"
        await _simulate_outline_ready(db_session, task["id"], outline_content)
        new_content = "# 修改大纲\n## 第一章 引言\n## 第二章 核心内容\n## 第三章 总结"
        resp = await client.post(
            f"/api/tasks/{task['id']}/outline/confirm",
            json={"content": new_content},
            headers=AUTH,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["confirmed"] is True
        assert data["content"] == new_content


# ---------------------------------------------------------------------------
# E2E Flow 3: 草稿续写流程
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestDraftContinuationFlow:
    @pytest.fixture(autouse=True)
    def _override_llm(self, mock_llm: MockLLMClient):
        app.dependency_overrides[get_llm_client] = lambda: mock_llm
        yield
        app.dependency_overrides.pop(get_llm_client, None)

    async def test_draft_task_creation_succeeds(self, client: AsyncClient):
        """带 draft_text 的任务创建成功"""
        task = await _create_task(client, DRAFT_PAYLOAD)
        assert task["id"] is not None
        assert task["mode"] == "report"

    async def test_draft_task_skips_outline_review(self, client: AsyncClient):
        """草稿任务不应进入 outline_review 状态，应跳过到写作阶段"""
        task = await _create_task(client, DRAFT_PAYLOAD)
        detail = await _get_task(client, task["id"])
        # 草稿任务的 FSM 应绕过大纲阶段
        assert detail["fsm_state"] != "outline_review"


# ---------------------------------------------------------------------------
# E2E Flow 4: 小说模式流程
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestNovelModeFlow:
    @pytest.fixture(autouse=True)
    def _override_llm(self, mock_llm: MockLLMClient):
        app.dependency_overrides[get_llm_client] = lambda: mock_llm
        yield
        app.dependency_overrides.pop(get_llm_client, None)

    async def test_novel_task_creation_succeeds(self, client: AsyncClient):
        """小说模式任务创建成功"""
        task = await _create_task(client, NOVEL_PAYLOAD)
        assert task["mode"] == "novel"
        assert task["target_words"] == 3000

    async def test_novel_task_visible_in_history_with_mode_filter(
        self, client: AsyncClient
    ):
        """历史任务页可按 mode=novel 过滤"""
        task = await _create_task(client, NOVEL_PAYLOAD)
        resp = await client.get("/api/tasks?mode=novel", headers=AUTH)
        data = resp.json()
        ids = [t["id"] for t in data["items"]]
        assert task["id"] in ids

    async def test_novel_completed_has_output(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """小说任务完成后有输出文本"""
        task = await _create_task(client, NOVEL_PAYLOAD)
        output = "# 虚空编年史\n\n" + "叙事内容。" * 300
        await _simulate_fsm_complete(db_session, task["id"], output, word_count=3000)
        detail = await _get_task(client, task["id"])
        assert detail["status"] == "completed"
        assert detail["output_text"] is not None


# ---------------------------------------------------------------------------
# E2E Flow 5: 自定义模式流程
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCustomModeFlow:
    @pytest.fixture(autouse=True)
    def _override_llm(self, mock_llm: MockLLMClient):
        app.dependency_overrides[get_llm_client] = lambda: mock_llm
        yield
        app.dependency_overrides.pop(get_llm_client, None)

    async def test_custom_task_creation_succeeds(self, client: AsyncClient):
        """自定义模式任务创建成功"""
        task = await _create_task(client, CUSTOM_PAYLOAD)
        assert task["mode"] == "custom"

    async def test_custom_task_batch_delete(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """批量删除测试：创建两个任务后批量删除"""
        t1 = await _create_task(client, CUSTOM_PAYLOAD)
        t2 = await _create_task(client, NOVEL_PAYLOAD)
        resp = await client.request(
            "DELETE", "/api/tasks",
            json={"ids": [t1["id"], t2["id"]]},
            headers=AUTH,
        )
        assert resp.status_code == 200
        assert resp.json()["deleted_count"] == 2
        # 验证已删除
        resp2 = await client.get("/api/tasks", headers=AUTH)
        ids = [t["id"] for t in resp2.json()["items"]]
        assert t1["id"] not in ids
        assert t2["id"] not in ids
