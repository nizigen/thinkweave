# Step 5.2 Event Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不破坏现有 WebSocket 握手与心跳能力的前提下，实现 Redis task events 到 WebSocket 客户端的共享桥接层。

**Architecture:** 保留 `ws.py` 负责连接生命周期，新增 `event_bridge.py` 维护每个 `task_id` 的单例 reader 协程；reader 使用 `xread_latest()` 拉取 Redis Stream 并通过 `ws_manager.broadcast()` 推送标准化事件。

**Tech Stack:** FastAPI WebSocket, asyncio, Redis Streams, Pydantic, pytest, pytest-asyncio

---

### Task 1: 补齐 WebSocket 事件 Schema

**Files:**
- Create: `backend/app/schemas/ws_event.py`
- Modify: `backend/app/schemas/__init__.py`
- Test: `backend/tests/test_event_bridge.py`

- [ ] **Step 1: 写失败测试**

为桥接层准备事件 schema 断言，至少包含 `node_update` 与 `connected` 的合法序列化。

- [ ] **Step 2: 运行测试确认失败**

Run: `backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_event_bridge.py -k schema`

- [ ] **Step 3: 写最小实现**

新增 `ws_event.py`，定义统一字段：
- `type`
- `task_id`
- `node_id`
- `from_agent`
- `timestamp`
- `payload`

- [ ] **Step 4: 运行测试确认通过**

Run: `backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_event_bridge.py -k schema`

### Task 2: 实现共享事件桥接器

**Files:**
- Create: `backend/app/services/event_bridge.py`
- Test: `backend/tests/test_event_bridge.py`

- [ ] **Step 1: 写失败测试**

覆盖：
- `ensure_started()` 幂等
- `stop()` 清理注册表
- `status_update` -> `node_update` 映射
- 无连接时自动退出

- [ ] **Step 2: 运行测试确认失败**

Run: `backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_event_bridge.py`

- [ ] **Step 3: 写最小实现**

实现：
- `TaskEventBridge.ensure_started(task_id)`
- `TaskEventBridge.stop(task_id)`
- 后台 reader loop
- Redis envelope 标准化与广播

- [ ] **Step 4: 运行测试确认通过**

Run: `backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_event_bridge.py`

### Task 3: 接入 WebSocket 路由生命周期

**Files:**
- Modify: `backend/app/routers/ws.py`
- Test: `backend/tests/test_ws_endpoint.py`

- [ ] **Step 1: 写失败测试**

新增断言：
- 连接成功后会触发 `event_bridge.ensure_started(task_id)`
- 最后一个连接断开时会触发 `event_bridge.stop(task_id)`

- [ ] **Step 2: 运行测试确认失败**

Run: `backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_ws_endpoint.py -k bridge`

- [ ] **Step 3: 写最小实现**

在连接注册后启动桥接；断开后按连接数决定是否停止桥接。

- [ ] **Step 4: 运行测试确认通过**

Run: `backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_ws_endpoint.py -k bridge`

### Task 4: 回归验证与文档同步

**Files:**
- Modify: `docs/progress.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: 运行目标测试集**

Run: `backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_ws_manager.py backend/tests/test_ws_endpoint.py backend/tests/test_event_bridge.py`

- [ ] **Step 2: 运行桥接相关回归**

Run: `backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_communicator.py backend/tests/test_redis_streams.py`

- [ ] **Step 3: 更新文档**

记录：
- Step 5.1 已验收
- Step 5.2 已实现共享桥接器与事件标准化

- [ ] **Step 4: 再跑一次最终验证**

Run: `backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_ws_manager.py backend/tests/test_ws_endpoint.py backend/tests/test_event_bridge.py backend/tests/test_communicator.py backend/tests/test_redis_streams.py`
