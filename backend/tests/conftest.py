"""Test configuration and fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import dotenv
import pytest
import pytest_asyncio

# Load .env so POSTGRES_URL and other settings are available during tests.
dotenv.load_dotenv(Path(__file__).parent.parent / ".env", override=False)
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import get_session
from app.main import app
from app.security.rate_limit import enforce_task_create_rate_limit
from app.services.dag_scheduler import stop_all_schedulers
from app.utils.llm_client import BaseLLMClient


# ---------------------------------------------------------------------------
# Mock LLM responses (按角色返回预设内容)
# ---------------------------------------------------------------------------

MOCK_OUTLINE = """# 大纲
## 第1章 引言
## 第2章 核心概念
## 第3章 总结"""

MOCK_CHAPTER = "这是一段模拟生成的章节内容，用于测试。" * 10

MOCK_REVIEW_JSON = {
    "score": 85,
    "accuracy_score": 90,
    "coherence_score": 80,
    "style_score": 85,
    "feedback": "内容结构清晰，论述完整。",
    "pass": True,
}

MOCK_DAG_JSON = {
    "nodes": [
        {"id": "n1", "title": "大纲生成", "role": "outline", "depends_on": []},
        {"id": "n2", "title": "第1章撰写", "role": "writer", "depends_on": ["n1"]},
        {"id": "n3", "title": "第2章撰写", "role": "writer", "depends_on": ["n1"]},
    ]
}


# ---------------------------------------------------------------------------
# MockLLMClient — 测试用，不调用任何外部API
# ---------------------------------------------------------------------------

class MockLLMClient(BaseLLMClient):
    """Mock LLM客户端：按角色返回预设响应，记录所有调用供断言"""

    def __init__(self) -> None:
        self.call_log: list[dict[str, Any]] = []

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        role: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
        max_retries: int | None = None,
        fallback_models: list[str] | None = None,
    ) -> str:
        self.call_log.append({
            "method": "chat", "role": role, "model": model,
            "max_retries": max_retries, "fallback_models": fallback_models,
            "messages": messages,
        })
        if role == "outline":
            return MOCK_OUTLINE
        if role == "writer":
            return MOCK_CHAPTER
        if role == "reviewer":
            return "审查通过，评分85分。"
        if role == "consistency":
            return "一致性检查通过，无问题。"
        return "mock response"

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        role: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
        max_retries: int | None = None,
        fallback_models: list[str] | None = None,
    ) -> AsyncIterator[str]:
        self.call_log.append({
            "method": "chat_stream", "role": role, "model": model,
            "max_retries": max_retries, "fallback_models": fallback_models,
        })
        chunks = ["这是", "一段", "流式", "输出", "测试。"]
        for chunk in chunks:
            yield chunk

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        role: str | None = None,
        schema: type | None = None,
        max_tokens: int | None = None,
        max_retries: int | None = None,
        fallback_models: list[str] | None = None,
    ) -> dict:
        self.call_log.append({
            "method": "chat_json", "role": role, "model": model,
            "max_retries": max_retries, "fallback_models": fallback_models,
            "messages": messages,
        })
        if role == "orchestrator":
            return MOCK_DAG_JSON
        if role == "reviewer":
            return MOCK_REVIEW_JSON
        return {"result": "mock"}

    async def chat_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        *,
        model: str | None = None,
        role: str | None = None,
        max_tokens: int | None = None,
        max_retries: int | None = None,
        fallback_models: list[str] | None = None,
        task_id: str = "",
        node_id: str = "",
    ) -> dict:
        self.call_log.append({
            "method": "chat_with_tools", "role": role, "tools": tools,
            "max_retries": max_retries, "fallback_models": fallback_models,
            "task_id": task_id, "node_id": node_id,
        })
        return {"type": "text", "content": "mock tool response"}

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        self.call_log.append({
            "method": "embed", "count": len(texts),
        })
        return [[0.1] * 1536 for _ in texts]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session():
    """Test session with a per-test engine — avoids event loop cross-contamination."""
    test_engine = create_async_engine(settings.postgres_url, echo=False)
    factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with factory() as session:
        yield session
        await session.rollback()

    await test_engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_scheduler_tasks():
    yield
    await stop_all_schedulers()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """Async HTTP test client with DB session override."""

    async def override_get_session():
        yield db_session

    async def noop_rate_limit(_user_id: str = "") -> None:
        pass

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[enforce_task_create_rate_limit] = noop_rate_limit
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def mock_llm():
    """Mock LLM客户端 — 所有测试默认使用，不调用外部API"""
    return MockLLMClient()


@pytest.fixture(autouse=True)
def _default_auth_settings():
    old_tokens = settings.task_auth_tokens
    old_admins = settings.admin_user_ids
    settings.task_auth_tokens = "token-admin:admin-user,token-user:test-user"
    settings.admin_user_ids = "admin-user"
    yield
    settings.task_auth_tokens = old_tokens
    settings.admin_user_ids = old_admins


@pytest.fixture(autouse=True)
def _disable_rate_limit_for_tests():
    """Keep task API tests deterministic without external Redis dependency."""
    old_disable = settings.disable_rate_limit
    settings.disable_rate_limit = True
    yield
    settings.disable_rate_limit = old_disable
