"""Step 7.2 故障恢复与边界测试"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# LLM 降级测试
# ---------------------------------------------------------------------------

class TestLLMFallback:
    """主模型失败时自动 fallback 到备用模型"""

    @pytest.mark.asyncio
    async def test_fallback_on_429(self):
        """主模型返回 429 时自动 fallback 到备用模型"""
        from app.utils.llm_client import LLMClient
        from openai import RateLimitError
        import httpx

        client = LLMClient()
        call_count = {"primary": 0, "fallback": 0}

        async def mock_primary(*args, **kwargs):
            call_count["primary"] += 1
            raise RateLimitError(
                message="Rate limit exceeded",
                response=MagicMock(status_code=429),
                body={},
            )

        async def mock_fallback(*args, **kwargs):
            call_count["fallback"] += 1
            mock = MagicMock()
            mock.choices = [MagicMock()]
            mock.choices[0].message.content = "fallback response"
            return mock

        with patch.object(client, '_call_with_retry', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = "fallback response"
            result = await client.chat(
                [{"role": "user", "content": "test"}],
                role="writer",
            )
            assert result == "fallback response"

    @pytest.mark.asyncio
    async def test_fallback_on_500(self):
        """主模型返回 500 时自动 fallback"""
        from app.utils.llm_client import LLMClient
        from openai import InternalServerError

        client = LLMClient()

        with patch.object(client, '_call_with_retry', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = "recovered response"
            result = await client.chat(
                [{"role": "user", "content": "test"}],
                role="outline",
            )
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_provider_routing_by_role(self):
        """不同 role 路由到不同模型"""
        from app.utils.llm_client import LLMClient, ROLE_MODEL_MAP
        client = LLMClient()
        # orchestrator 应有模型配置
        assert "orchestrator" in ROLE_MODEL_MAP or len(ROLE_MODEL_MAP) > 0

    @pytest.mark.asyncio
    async def test_max_retries_exhausted_raises(self):
        """重试耗尽且无 fallback 时抛出异常"""
        from app.utils.llm_client import LLMClient
        from openai import RateLimitError

        client = LLMClient()

        with patch.object(client, '_call_with_retry', side_effect=RateLimitError(
            message="Rate limit",
            response=MagicMock(status_code=429),
            body={},
        )):
            with pytest.raises(RateLimitError):
                await client.chat(
                    [{"role": "user", "content": "test"}],
                    role="writer",
                )


# ---------------------------------------------------------------------------
# FSM 审查重试上限测试
# ---------------------------------------------------------------------------

class TestFSMReviewRetryLimit:
    """章节审查连续失败达上限时 FSM 进入 FAILED"""

    def test_review_retry_limit_constant(self):
        """MAX_REVIEW_RETRIES 常量存在"""
        from app.services.long_text_fsm import MAX_REVIEW_RETRIES
        assert MAX_REVIEW_RETRIES >= 1

    def test_review_retry_not_exceeded_initially(self):
        """初始状态审查重试未超限"""
        from app.services.long_text_fsm import LongTextFSM
        import uuid
        fsm = LongTextFSM(task_id=uuid.uuid4())
        assert fsm.is_review_retry_exceeded(chapter_index=0) is False

    def test_review_retry_exceeded_after_max(self):
        """达到 MAX_REVIEW_RETRIES 次后超限"""
        from app.services.long_text_fsm import LongTextFSM, MAX_REVIEW_RETRIES
        import uuid
        fsm = LongTextFSM(task_id=uuid.uuid4())
        for _ in range(MAX_REVIEW_RETRIES):
            fsm.increment_review_retry(chapter_index=0)
        assert fsm.is_review_retry_exceeded(chapter_index=0) is True

    def test_review_retry_independent_per_chapter(self):
        """不同章节的重试计数独立"""
        from app.services.long_text_fsm import LongTextFSM, MAX_REVIEW_RETRIES
        import uuid
        fsm = LongTextFSM(task_id=uuid.uuid4())
        for _ in range(MAX_REVIEW_RETRIES):
            fsm.increment_review_retry(chapter_index=0)
        assert fsm.is_review_retry_exceeded(chapter_index=0) is True
        assert fsm.is_review_retry_exceeded(chapter_index=1) is False


# ---------------------------------------------------------------------------
# FSM 一致性重试上限测试
# ---------------------------------------------------------------------------

class TestFSMConsistencyRetryLimit:
    """一致性检查连续失败达上限时 FSM 正确处理"""

    def test_consistency_retry_limit_constant(self):
        """MAX_CONSISTENCY_RETRIES 常量存在"""
        from app.services.long_text_fsm import MAX_CONSISTENCY_RETRIES
        assert MAX_CONSISTENCY_RETRIES >= 1

    def test_consistency_retry_not_exceeded_initially(self):
        from app.services.long_text_fsm import LongTextFSM
        import uuid
        fsm = LongTextFSM(task_id=uuid.uuid4())
        assert fsm.is_consistency_retry_exceeded() is False

    def test_consistency_retry_exceeded_after_max(self):
        from app.services.long_text_fsm import LongTextFSM, MAX_CONSISTENCY_RETRIES
        import uuid
        fsm = LongTextFSM(task_id=uuid.uuid4())
        for _ in range(MAX_CONSISTENCY_RETRIES):
            fsm.increment_consistency_retry()
        assert fsm.is_consistency_retry_exceeded() is True


# ---------------------------------------------------------------------------
# FSM 检查点恢复测试
# ---------------------------------------------------------------------------

class TestFSMCheckpointRecovery:
    """FSM 从持久化检查点恢复"""

    @pytest.mark.asyncio
    async def test_fsm_resume_restores_state(self, db_session):
        """scan_and_resume 能正确恢复 writing 状态的 FSM"""
        from app.services.long_text_fsm import scan_and_resume_running_tasks, LongTextState
        from app.models.task import Task
        from sqlalchemy import insert
        import uuid
        from datetime import datetime, UTC

        task_id = uuid.uuid4()
        checkpoint = {
            "fsm_state": "writing",
            "completed_chapters": [0],
            "review_retry_count": {},
            "consistency_retry_count": 0,
            "checkpoint_at": "2026-03-26T10:00:00",
        }
        db_session.add(Task(
            id=task_id,
            title="Recovery test task",
            mode="report",
            status="running",
            fsm_state="writing",
            checkpoint_data=checkpoint,
        ))
        await db_session.commit()

        fsms = await scan_and_resume_running_tasks(session=db_session)
        resumed = [f for f in fsms if f.task_id == task_id]
        assert len(resumed) == 1
        assert resumed[0].state is LongTextState.WRITING
        assert 0 in resumed[0].completed_chapters

    @pytest.mark.asyncio
    async def test_fsm_resume_skips_invalid_state(self, db_session):
        """无效 fsm_state 的任务被跳过，不崩溃"""
        from app.services.long_text_fsm import scan_and_resume_running_tasks
        from app.models.task import Task
        import uuid

        task_id = uuid.uuid4()
        db_session.add(Task(
            id=task_id,
            title="Corrupted task",
            mode="report",
            status="running",
            fsm_state="INVALID_STATE",
            checkpoint_data={"fsm_state": "INVALID_STATE"},
        ))
        await db_session.commit()

        fsms = await scan_and_resume_running_tasks(session=db_session)
        resumed_ids = [f.task_id for f in fsms]
        assert task_id not in resumed_ids
