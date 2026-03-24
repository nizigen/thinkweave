# Step 5.3 Agent Events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Phase 5 实时监控链路补齐 Agent/FSM 侧事件发射，让 WebSocket 桥接层能够拿到完整的节点状态、章节预览、审查评分、一致性结果和任务终态事件。

**Architecture:** 在 `communicator.py` 增加通用任务事件发送入口，保留现有 `send_status_update()` 兼容层；`LoggingMiddleware` 发 `node_update`，`BaseAgent` 发角色相关事件，`DAGScheduler` 发 `task_done`，`LongTextFSM` 通过可注入事件发送器为状态迁移发 `dag_update`。

**Tech Stack:** FastAPI backend, Redis Streams, asyncio, pytest, pytest-asyncio

---

### Task 1: 通用任务事件发送入口

**Files:**
- Modify: `backend/app/services/communicator.py`
- Modify: `backend/tests/test_communicator.py`

- [ ] **Step 1: 写失败测试**
- [ ] **Step 2: 运行测试确认失败**
- [ ] **Step 3: 实现 `send_task_event()`，并让 `send_status_update()` 走兼容封装**
- [ ] **Step 4: 运行测试确认通过**

### Task 2: LoggingMiddleware 发 node_update

**Files:**
- Modify: `backend/app/agents/middleware.py`
- Modify: `backend/tests/test_agent_core.py`

- [ ] **Step 1: 写失败测试**
- [ ] **Step 2: 运行测试确认失败**
- [ ] **Step 3: 在 before/after/on_error 中发送 `node_update`**
- [ ] **Step 4: 运行测试确认通过**

### Task 3: Agent 专属事件发射

**Files:**
- Modify: `backend/app/agents/base_agent.py`
- Modify: `backend/tests/test_agent_core.py`

- [ ] **Step 1: 写失败测试**
- [ ] **Step 2: 运行测试确认失败**
- [ ] **Step 3: 成功路径发 `chapter_preview` / `review_score` / `consistency_result`，失败和完成路径补齐节点事件**
- [ ] **Step 4: 运行测试确认通过**

### Task 4: 任务终态与 FSM 状态事件

**Files:**
- Modify: `backend/app/services/dag_scheduler.py`
- Modify: `backend/app/services/long_text_fsm.py`
- Modify: `backend/tests/test_dag_scheduler.py`
- Modify: `backend/tests/test_long_text_fsm.py`

- [ ] **Step 1: 写失败测试**
- [ ] **Step 2: 运行测试确认失败**
- [ ] **Step 3: `_mark_task_done/_mark_task_failed` 发 `task_done`；FSM 通过可注入 sender 发 `dag_update`**
- [ ] **Step 4: 运行测试确认通过**

### Task 5: 文档与最终验证

**Files:**
- Modify: `docs/progress.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`
- Modify: `docs/task_plan.md`

- [ ] **Step 1: 运行目标测试集**
- [ ] **Step 2: 更新 Phase 5 文档状态**
- [ ] **Step 3: 再跑一次最终验证命令**
