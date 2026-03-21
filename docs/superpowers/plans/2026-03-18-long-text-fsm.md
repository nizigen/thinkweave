# Step 4.1 长文本FSM Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现长文本生成的有限状态机（FSM），支持 7 状态流转、检查点持久化和崩溃恢复

**Architecture:** 事件钩子模式 — FSM 管理状态转换和检查点，通过 `on_enter_{state}()` 回调接口与外部系统解耦。Step 4.2 填充 Agent 实现，Step 4.3 填充调度集成。

**Tech Stack:** Python 3.13, SQLAlchemy 2.0 async, Alembic, pytest-asyncio

---

## File Structure

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `backend/app/services/long_text_fsm.py` | FSM 核心：状态定义、转换规则、事件钩子、checkpoint、resume |
| Modify | `backend/app/models/task.py` | 添加 checkpoint_data JSONB + error_message Text 列 |
| Create | `backend/migrations/versions/xxx_add_checkpoint_data.py` | Alembic 迁移 |
| Create | `backend/tests/test_long_text_fsm.py` | FSM 单元测试 |

---

## Chunk 1: Task 模型扩展 + Alembic 迁移

### Task 1: 添加 checkpoint_data 和 error_message 到 Task 模型

**Files:**
- Modify: `backend/app/models/task.py:6,23-32`
- Create: Alembic migration

- [ ] **Step 1.1: 修改 Task ORM 模型 — 添加两个新列**

```python
# backend/app/models/task.py — 添加 import
from sqlalchemy import String, Text, Integer, SmallInteger, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB  # 新增 JSONB

# Task 类中添加两个字段（在 target_words 之后、created_at 之前）:
    checkpoint_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 1.2: 生成 Alembic 迁移**

```bash
cd backend && python -m alembic revision --autogenerate -m "add checkpoint_data and error_message to tasks"
```

- [ ] **Step 1.3: 检查生成的迁移文件，确认只有两列变更**

- [ ] **Step 1.4: 运行迁移（需要 Docker PostgreSQL 运行）**

```bash
cd backend && python -m alembic upgrade head
```

- [ ] **Step 1.5: Commit**

```bash
git add backend/app/models/task.py backend/migrations/
git commit -m "feat: add checkpoint_data JSONB and error_message to tasks table"
```

---

## Chunk 2: FSM 核心 — 状态定义 + 转换规则

### Task 2: FSM 状态枚举 + 转换验证

**Files:**
- Create: `backend/app/services/long_text_fsm.py`
- Create: `backend/tests/test_long_text_fsm.py`

- [ ] **Step 2.1: RED — 写状态定义和转换验证的测试**

```python
# backend/tests/test_long_text_fsm.py
from __future__ import annotations

import pytest

from app.services.long_text_fsm import (
    FSMState,
    FSMTransitionError,
    LongTextFSM,
    FSM_TRANSITIONS,
    MAX_REVIEW_RETRIES,
    MAX_CONSISTENCY_RETRIES,
    REVIEW_PASS_THRESHOLD,
)


class TestFSMStates:
    """FSM 状态定义和常量"""

    def test_all_states_defined(self):
        states = {s.value for s in FSMState}
        assert states == {
            "init", "outline", "outline_review",
            "writing", "reviewing", "consistency",
            "done", "failed",
        }

    def test_constants(self):
        assert MAX_REVIEW_RETRIES == 3
        assert MAX_CONSISTENCY_RETRIES == 2
        assert REVIEW_PASS_THRESHOLD == 70


class TestFSMTransitions:
    """FSM 状态转换规则"""

    def test_valid_transitions(self):
        fsm = LongTextFSM()
        assert fsm.state == FSMState.INIT
        assert fsm.can_transition(FSMState.OUTLINE)

    def test_invalid_transition_raises(self):
        fsm = LongTextFSM()
        with pytest.raises(FSMTransitionError):
            fsm.transition(FSMState.WRITING)  # INIT 不能直接到 WRITING

    def test_full_happy_path(self):
        """完整正常流程: INIT→OUTLINE→OUTLINE_REVIEW→WRITING→REVIEWING→CONSISTENCY→DONE"""
        fsm = LongTextFSM()
        for target in [
            FSMState.OUTLINE,
            FSMState.OUTLINE_REVIEW,
            FSMState.WRITING,
            FSMState.REVIEWING,
            FSMState.CONSISTENCY,
            FSMState.DONE,
        ]:
            fsm.transition(target)
        assert fsm.state == FSMState.DONE

    def test_review_retry_loop(self):
        """审查不通过 → 回到 WRITING"""
        fsm = LongTextFSM()
        fsm.transition(FSMState.OUTLINE)
        fsm.transition(FSMState.OUTLINE_REVIEW)
        fsm.transition(FSMState.WRITING)
        fsm.transition(FSMState.REVIEWING)
        fsm.transition(FSMState.WRITING)  # 退回重写
        assert fsm.state == FSMState.WRITING

    def test_consistency_retry_loop(self):
        """一致性不通过 → 回到 WRITING"""
        fsm = LongTextFSM()
        fsm.transition(FSMState.OUTLINE)
        fsm.transition(FSMState.OUTLINE_REVIEW)
        fsm.transition(FSMState.WRITING)
        fsm.transition(FSMState.REVIEWING)
        fsm.transition(FSMState.CONSISTENCY)
        fsm.transition(FSMState.WRITING)  # 退回修改
        assert fsm.state == FSMState.WRITING

    def test_any_state_can_fail(self):
        """任何状态都可以转到 FAILED"""
        for start in [FSMState.OUTLINE, FSMState.WRITING, FSMState.REVIEWING]:
            fsm = LongTextFSM(initial_state=start)
            fsm.transition(FSMState.FAILED)
            assert fsm.state == FSMState.FAILED

    def test_done_is_terminal(self):
        """DONE 不能再转换"""
        fsm = LongTextFSM(initial_state=FSMState.DONE)
        with pytest.raises(FSMTransitionError):
            fsm.transition(FSMState.WRITING)
```

- [ ] **Step 2.2: 运行测试确认全部 FAIL**

```bash
cd backend && python -m pytest tests/test_long_text_fsm.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.long_text_fsm'`

- [ ] **Step 2.3: GREEN — 实现 FSM 核心（状态 + 转换）**

```python
# backend/app/services/long_text_fsm.py
from __future__ import annotations

from enum import Enum

from app.utils.logger import logger


# === Constants ===

MAX_REVIEW_RETRIES = 3
MAX_CONSISTENCY_RETRIES = 2
REVIEW_PASS_THRESHOLD = 70


# === States ===

class FSMState(str, Enum):
    INIT = "init"
    OUTLINE = "outline"
    OUTLINE_REVIEW = "outline_review"
    WRITING = "writing"
    REVIEWING = "reviewing"
    CONSISTENCY = "consistency"
    DONE = "done"
    FAILED = "failed"


# === Transitions ===

FSM_TRANSITIONS: dict[FSMState, set[FSMState]] = {
    FSMState.INIT: {FSMState.OUTLINE, FSMState.FAILED},
    FSMState.OUTLINE: {FSMState.OUTLINE_REVIEW, FSMState.FAILED},
    FSMState.OUTLINE_REVIEW: {FSMState.WRITING, FSMState.FAILED},
    FSMState.WRITING: {FSMState.REVIEWING, FSMState.FAILED},
    FSMState.REVIEWING: {FSMState.WRITING, FSMState.CONSISTENCY, FSMState.FAILED},
    FSMState.CONSISTENCY: {FSMState.WRITING, FSMState.DONE, FSMState.FAILED},
    FSMState.DONE: set(),
    FSMState.FAILED: set(),
}


# === Exceptions ===

class FSMTransitionError(Exception):
    def __init__(self, current: FSMState, target: FSMState) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"Invalid FSM transition: {current.value} → {target.value}. "
            f"Allowed: {[s.value for s in FSM_TRANSITIONS.get(current, set())]}"
        )


# === FSM ===

class LongTextFSM:
    """长文本生成有限状态机"""

    def __init__(self, initial_state: FSMState = FSMState.INIT) -> None:
        self._state = initial_state
        self._log = logger.bind(component="fsm")

    @property
    def state(self) -> FSMState:
        return self._state

    def can_transition(self, target: FSMState) -> bool:
        return target in FSM_TRANSITIONS.get(self._state, set())

    def transition(self, target: FSMState) -> FSMState:
        if not self.can_transition(target):
            raise FSMTransitionError(self._state, target)
        prev = self._state
        self._state = target
        self._log.info(
            "FSM transition",
            prev=prev.value,
            new=target.value,
        )
        return self._state
```

- [ ] **Step 2.4: 运行测试确认全部 PASS**

```bash
cd backend && python -m pytest tests/test_long_text_fsm.py -v
```

- [ ] **Step 2.5: Commit**

```bash
git add backend/app/services/long_text_fsm.py backend/tests/test_long_text_fsm.py
git commit -m "feat: implement FSM core — states, transitions, validation"
```

---

## Chunk 3: 事件钩子 + 重试计数

### Task 3: on_enter 回调 + 重试计数器

**Files:**
- Modify: `backend/app/services/long_text_fsm.py`
- Modify: `backend/tests/test_long_text_fsm.py`

- [ ] **Step 3.1: RED — 写事件钩子和重试计数的测试**

```python
# 追加到 backend/tests/test_long_text_fsm.py

from unittest.mock import AsyncMock
import pytest_asyncio


class TestFSMEventHooks:
    """事件钩子回调"""

    @pytest.mark.asyncio
    async def test_on_enter_called_on_transition(self):
        hook = AsyncMock()
        fsm = LongTextFSM()
        fsm.register_hook(FSMState.OUTLINE, hook)
        await fsm.async_transition(FSMState.OUTLINE)
        hook.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multiple_hooks_called_in_order(self):
        call_order = []
        hook_a = AsyncMock(side_effect=lambda _: call_order.append("a"))
        hook_b = AsyncMock(side_effect=lambda _: call_order.append("b"))
        fsm = LongTextFSM()
        fsm.register_hook(FSMState.OUTLINE, hook_a)
        fsm.register_hook(FSMState.OUTLINE, hook_b)
        await fsm.async_transition(FSMState.OUTLINE)
        assert call_order == ["a", "b"]

    @pytest.mark.asyncio
    async def test_hook_receives_fsm_context(self):
        received = {}
        async def capture_hook(ctx):
            received.update(ctx)
        fsm = LongTextFSM()
        fsm.register_hook(FSMState.OUTLINE, capture_hook)
        await fsm.async_transition(FSMState.OUTLINE)
        assert received["prev_state"] == FSMState.INIT
        assert received["new_state"] == FSMState.OUTLINE


class TestFSMRetryCounters:
    """重试计数"""

    def test_review_retry_increments(self):
        fsm = LongTextFSM(initial_state=FSMState.REVIEWING)
        fsm.transition(FSMState.WRITING)  # 审查退回
        assert fsm.review_retry_count == 1

    def test_review_retry_max_exceeded_forces_fail(self):
        fsm = LongTextFSM(initial_state=FSMState.REVIEWING)
        fsm._review_retry_count = MAX_REVIEW_RETRIES
        with pytest.raises(FSMTransitionError, match="max retries"):
            fsm.transition(FSMState.WRITING)

    def test_consistency_retry_increments(self):
        fsm = LongTextFSM(initial_state=FSMState.CONSISTENCY)
        fsm.transition(FSMState.WRITING)
        assert fsm.consistency_retry_count == 1

    def test_consistency_retry_max_exceeded_forces_fail(self):
        fsm = LongTextFSM(initial_state=FSMState.CONSISTENCY)
        fsm._consistency_retry_count = MAX_CONSISTENCY_RETRIES
        with pytest.raises(FSMTransitionError, match="max retries"):
            fsm.transition(FSMState.WRITING)

    def test_review_retry_resets_on_consistency(self):
        """进入 CONSISTENCY 阶段后，review retry 计数重置"""
        fsm = LongTextFSM(initial_state=FSMState.REVIEWING)
        fsm._review_retry_count = 2
        fsm.transition(FSMState.CONSISTENCY)
        assert fsm.review_retry_count == 0
```

- [ ] **Step 3.2: 运行测试确认新测试 FAIL，旧测试仍 PASS**

```bash
cd backend && python -m pytest tests/test_long_text_fsm.py -v
```

- [ ] **Step 3.3: GREEN — 添加事件钩子 + 重试计数到 LongTextFSM**

在 `long_text_fsm.py` 的 `LongTextFSM` 类中扩展：

```python
class LongTextFSM:
    def __init__(self, initial_state: FSMState = FSMState.INIT) -> None:
        self._state = initial_state
        self._hooks: dict[FSMState, list[...]] = {}
        self._review_retry_count = 0
        self._consistency_retry_count = 0
        self._log = logger.bind(component="fsm")

    @property
    def review_retry_count(self) -> int:
        return self._review_retry_count

    @property
    def consistency_retry_count(self) -> int:
        return self._consistency_retry_count

    def register_hook(self, state: FSMState, hook) -> None:
        self._hooks.setdefault(state, []).append(hook)

    def transition(self, target: FSMState) -> FSMState:
        if not self.can_transition(target):
            raise FSMTransitionError(self._state, target)
        # Retry guard
        if self._state == FSMState.REVIEWING and target == FSMState.WRITING:
            if self._review_retry_count >= MAX_REVIEW_RETRIES:
                raise FSMTransitionError(self._state, target,
                    reason=f"Review max retries ({MAX_REVIEW_RETRIES}) exceeded")
            self._review_retry_count += 1
        if self._state == FSMState.CONSISTENCY and target == FSMState.WRITING:
            if self._consistency_retry_count >= MAX_CONSISTENCY_RETRIES:
                raise FSMTransitionError(self._state, target,
                    reason=f"Consistency max retries ({MAX_CONSISTENCY_RETRIES}) exceeded")
            self._consistency_retry_count += 1
        # Reset review count on entering consistency
        if target == FSMState.CONSISTENCY:
            self._review_retry_count = 0
        prev = self._state
        self._state = target
        self._log.info("FSM transition", prev=prev.value, new=target.value)
        return self._state

    async def async_transition(self, target: FSMState) -> FSMState:
        result = self.transition(target)
        ctx = {"prev_state": FSM_TRANSITIONS and self._state != target and prev or self._state,
               "new_state": target}
        # 简化: 构建 context
        for hook in self._hooks.get(target, []):
            await hook(ctx)
        return result
```

注意：`FSMTransitionError` 需要支持 `reason` 参数（更新 `__init__`）。

- [ ] **Step 3.4: 运行全部测试确认 PASS**

```bash
cd backend && python -m pytest tests/test_long_text_fsm.py -v
```

- [ ] **Step 3.5: Commit**

```bash
git add backend/app/services/long_text_fsm.py backend/tests/test_long_text_fsm.py
git commit -m "feat: add FSM event hooks and retry counters"
```

---

## Chunk 4: Checkpoint + Resume

### Task 4: 检查点持久化 + 崩溃恢复

**Files:**
- Modify: `backend/app/services/long_text_fsm.py`
- Modify: `backend/tests/test_long_text_fsm.py`

- [ ] **Step 4.1: RED — 写 checkpoint/resume 测试**

```python
# 追加到 backend/tests/test_long_text_fsm.py

class TestFSMCheckpoint:
    """检查点序列化"""

    def test_to_checkpoint_captures_state(self):
        fsm = LongTextFSM(initial_state=FSMState.WRITING)
        fsm._review_retry_count = 1
        cp = fsm.to_checkpoint(
            completed_chapters=[0, 1],
            active_nodes=["node-uuid-1"],
        )
        assert cp["fsm_state"] == "writing"
        assert cp["completed_chapters"] == [0, 1]
        assert cp["review_retry_count"] == 1
        assert cp["consistency_retry_count"] == 0
        assert cp["active_nodes"] == ["node-uuid-1"]
        assert "checkpoint_at" in cp

    def test_from_checkpoint_restores_state(self):
        cp = {
            "fsm_state": "reviewing",
            "completed_chapters": [0, 1, 2],
            "review_retry_count": 2,
            "consistency_retry_count": 0,
            "active_nodes": [],
            "checkpoint_at": "2026-03-18T12:00:00",
        }
        fsm = LongTextFSM.from_checkpoint(cp)
        assert fsm.state == FSMState.REVIEWING
        assert fsm.review_retry_count == 2
        assert fsm.consistency_retry_count == 0

    def test_from_checkpoint_invalid_state_raises(self):
        cp = {"fsm_state": "nonexistent"}
        with pytest.raises(ValueError, match="Unknown FSM state"):
            LongTextFSM.from_checkpoint(cp)


class TestFSMResume:
    """崩溃恢复"""

    def test_resume_skips_completed_chapters(self):
        cp = {
            "fsm_state": "writing",
            "completed_chapters": [0, 1, 3],
            "review_retry_count": 0,
            "consistency_retry_count": 0,
            "active_nodes": ["uuid-1"],
            "checkpoint_at": "2026-03-18T12:00:00",
        }
        fsm = LongTextFSM.from_checkpoint(cp)
        assert fsm.state == FSMState.WRITING
        assert fsm.completed_chapters == [0, 1, 3]

    def test_resume_preserves_retry_counts(self):
        cp = {
            "fsm_state": "reviewing",
            "completed_chapters": [0],
            "review_retry_count": 2,
            "consistency_retry_count": 1,
            "active_nodes": [],
            "checkpoint_at": "2026-03-18T12:00:00",
        }
        fsm = LongTextFSM.from_checkpoint(cp)
        assert fsm.review_retry_count == 2
        assert fsm.consistency_retry_count == 1
```

- [ ] **Step 4.2: 运行测试确认新测试 FAIL**

```bash
cd backend && python -m pytest tests/test_long_text_fsm.py::TestFSMCheckpoint -v
cd backend && python -m pytest tests/test_long_text_fsm.py::TestFSMResume -v
```

- [ ] **Step 4.3: GREEN — 实现 checkpoint/resume**

```python
# 追加到 LongTextFSM 类中

    @property
    def completed_chapters(self) -> list[int]:
        return list(self._completed_chapters)

    def to_checkpoint(
        self,
        completed_chapters: list[int] | None = None,
        active_nodes: list[str] | None = None,
    ) -> dict:
        return {
            "fsm_state": self._state.value,
            "completed_chapters": completed_chapters or [],
            "review_retry_count": self._review_retry_count,
            "consistency_retry_count": self._consistency_retry_count,
            "active_nodes": active_nodes or [],
            "checkpoint_at": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def from_checkpoint(cls, data: dict) -> LongTextFSM:
        state_str = data.get("fsm_state", "")
        try:
            state = FSMState(state_str)
        except ValueError:
            raise ValueError(f"Unknown FSM state: '{state_str}'")
        fsm = cls(initial_state=state)
        fsm._review_retry_count = data.get("review_retry_count", 0)
        fsm._consistency_retry_count = data.get("consistency_retry_count", 0)
        fsm._completed_chapters = list(data.get("completed_chapters", []))
        return fsm
```

- [ ] **Step 4.4: 运行全部测试确认 PASS**

```bash
cd backend && python -m pytest tests/test_long_text_fsm.py -v
```

- [ ] **Step 4.5: REFACTOR — 检查代码，确保文件 < 400 行，函数 < 50 行**

- [ ] **Step 4.6: Commit**

```bash
git add backend/app/services/long_text_fsm.py backend/tests/test_long_text_fsm.py
git commit -m "feat: add FSM checkpoint serialization and resume from crash"
```

---

## Chunk 5: DB 持久化 + 服务启动恢复

### Task 5: persist_checkpoint + resume_running_tasks

**Files:**
- Modify: `backend/app/services/long_text_fsm.py`
- Modify: `backend/tests/test_long_text_fsm.py`

- [ ] **Step 5.1: RED — 写 DB 持久化测试（需 db_session fixture）**

```python
# 追加到 backend/tests/test_long_text_fsm.py

import uuid
from app.models.task import Task


class TestFSMPersistence:
    """DB 持久化集成测试（需要 Docker PostgreSQL）"""

    @pytest.mark.asyncio
    async def test_persist_checkpoint_writes_to_db(self, db_session):
        task = Task(id=uuid.uuid4(), title="test", mode="report", status="running")
        db_session.add(task)
        await db_session.flush()

        fsm = LongTextFSM(initial_state=FSMState.WRITING)
        await persist_checkpoint(db_session, task.id, fsm, completed_chapters=[0, 1])

        await db_session.refresh(task)
        assert task.checkpoint_data is not None
        assert task.checkpoint_data["fsm_state"] == "writing"
        assert task.fsm_state == "writing"

    @pytest.mark.asyncio
    async def test_load_and_resume(self, db_session):
        task = Task(
            id=uuid.uuid4(), title="test", mode="report", status="running",
            fsm_state="reviewing",
            checkpoint_data={
                "fsm_state": "reviewing",
                "completed_chapters": [0, 1],
                "review_retry_count": 1,
                "consistency_retry_count": 0,
                "active_nodes": [],
                "checkpoint_at": "2026-03-18T12:00:00",
            },
        )
        db_session.add(task)
        await db_session.flush()

        fsm = await load_fsm_from_task(db_session, task.id)
        assert fsm.state == FSMState.REVIEWING
        assert fsm.review_retry_count == 1

    @pytest.mark.asyncio
    async def test_resume_running_tasks_on_startup(self, db_session):
        t1 = Task(id=uuid.uuid4(), title="running1", mode="report", status="running",
                   fsm_state="writing", checkpoint_data={"fsm_state": "writing",
                   "completed_chapters": [], "review_retry_count": 0,
                   "consistency_retry_count": 0, "active_nodes": [], "checkpoint_at": ""})
        t2 = Task(id=uuid.uuid4(), title="done1", mode="report", status="done")
        db_session.add_all([t1, t2])
        await db_session.flush()

        tasks = await find_resumable_tasks(db_session)
        assert len(tasks) == 1
        assert tasks[0].id == t1.id
```

- [ ] **Step 5.2: 运行测试确认 FAIL**

```bash
cd backend && python -m pytest tests/test_long_text_fsm.py::TestFSMPersistence -v
```

- [ ] **Step 5.3: GREEN — 实现持久化函数**

```python
# 追加到 backend/app/services/long_text_fsm.py

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task


async def persist_checkpoint(
    session: AsyncSession,
    task_id: uuid.UUID,
    fsm: LongTextFSM,
    completed_chapters: list[int] | None = None,
    active_nodes: list[str] | None = None,
) -> None:
    cp = fsm.to_checkpoint(completed_chapters, active_nodes)
    await session.execute(
        update(Task)
        .where(Task.id == task_id)
        .values(checkpoint_data=cp, fsm_state=fsm.state.value)
    )
    await session.flush()


async def load_fsm_from_task(
    session: AsyncSession,
    task_id: uuid.UUID,
) -> LongTextFSM:
    result = await session.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one()
    if task.checkpoint_data:
        return LongTextFSM.from_checkpoint(task.checkpoint_data)
    return LongTextFSM(initial_state=FSMState(task.fsm_state))


async def find_resumable_tasks(session: AsyncSession) -> list[Task]:
    result = await session.execute(
        select(Task).where(Task.status == "running")
    )
    return list(result.scalars().all())
```

- [ ] **Step 5.4: 运行全部测试确认 PASS**

```bash
cd backend && python -m pytest tests/test_long_text_fsm.py -v
```

- [ ] **Step 5.5: Commit**

```bash
git add backend/app/services/long_text_fsm.py backend/tests/test_long_text_fsm.py
git commit -m "feat: add FSM DB persistence, load, and startup resume scan"
```

---

## Final Checklist

- [ ] 所有测试 PASS（`pytest tests/test_long_text_fsm.py -v`）
- [ ] `long_text_fsm.py` < 400 行
- [ ] 无 unused imports
- [ ] progress.md 更新
- [ ] IMPLEMENTATION_PLAN.md 中 Step 4.1 checkbox 标记为 [x]
