# Step 5.1 WebSocket 后端基础设施 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `/ws/task/{task_id}` WebSocket 端点，支持多客户端并发订阅、应用层心跳（30s ping / 60s 超时断开）、握手鉴权（task_id 不存在返回 404）。

**Architecture:** `WebSocketManager` 维护 `task_id → set[WebSocket]` 映射，提供 connect/disconnect/broadcast 三个核心方法；心跳作为独立 asyncio.Task 运行，60s 无 pong 触发主动断开；路由层负责鉴权和生命周期管理。

**Tech Stack:** FastAPI WebSocket, asyncio, pytest + pytest-asyncio, httpx (TestClient for WS)

---

## Task 1: WebSocketManager 核心（connect/disconnect/broadcast）

**Files:**
- Create: `backend/app/services/ws_manager.py`
- Create: `backend/tests/test_ws_manager.py`

- [ ] **Step 1: 写失败测试 — connect 注册连接**

```python
# backend/tests/test_ws_manager.py
import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.services.ws_manager import WebSocketManager


@pytest.fixture
def manager():
    return WebSocketManager()


@pytest.fixture
def mock_ws():
    ws = MagicMock()
    ws.send_text = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_connect_registers_websocket(manager, mock_ws):
    task_id = "task-001"
    await manager.connect(task_id, mock_ws)
    assert mock_ws in manager.get_connections(task_id)


@pytest.mark.asyncio
async def test_disconnect_removes_websocket(manager, mock_ws):
    task_id = "task-001"
    await manager.connect(task_id, mock_ws)
    manager.disconnect(task_id, mock_ws)
    assert mock_ws not in manager.get_connections(task_id)


@pytest.mark.asyncio
async def test_disconnect_unknown_task_no_error(manager, mock_ws):
    """Disconnecting a WS that was never registered should not raise."""
    manager.disconnect("nonexistent", mock_ws)  # should not raise


@pytest.mark.asyncio
async def test_broadcast_sends_to_all_connections(manager):
    task_id = "task-001"
    ws1, ws2 = MagicMock(), MagicMock()
    ws1.send_text = AsyncMock()
    ws2.send_text = AsyncMock()
    await manager.connect(task_id, ws1)
    await manager.connect(task_id, ws2)
    await manager.broadcast(task_id, {"type": "test", "data": "hello"})
    ws1.send_text.assert_awaited_once()
    ws2.send_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_broadcast_skips_failed_connection(manager):
    """If one connection raises on send, others still receive the message."""
    task_id = "task-001"
    ws_ok = MagicMock()
    ws_ok.send_text = AsyncMock()
    ws_fail = MagicMock()
    ws_fail.send_text = AsyncMock(side_effect=Exception("broken pipe"))
    await manager.connect(task_id, ws_ok)
    await manager.connect(task_id, ws_fail)
    await manager.broadcast(task_id, {"type": "test"})  # should not raise
    ws_ok.send_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_multiple_tasks_isolated(manager):
    """Connections for different task_ids must not receive each other's messages."""
    ws_a, ws_b = MagicMock(), MagicMock()
    ws_a.send_text = AsyncMock()
    ws_b.send_text = AsyncMock()
    await manager.connect("task-A", ws_a)
    await manager.connect("task-B", ws_b)
    await manager.broadcast("task-A", {"type": "test"})
    ws_a.send_text.assert_awaited_once()
    ws_b.send_text.assert_not_awaited()
```

- [ ] **Step 2: 运行测试确认全部 FAIL**

```bash
cd backend
pytest tests/test_ws_manager.py -v
```

期望输出：`ImportError: cannot import name 'WebSocketManager'`

- [ ] **Step 3: 实现 WebSocketManager（GREEN）**

```python
# backend/app/services/ws_manager.py
"""WebSocket 连接管理器"""

import asyncio
import json
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

from app.utils.logger import logger


class WebSocketManager:
    """维护 task_id → set[WebSocket] 映射，提供 connect/disconnect/broadcast。"""

    def __init__(self) -> None:
        # task_id -> set of active WebSocket connections
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    def get_connections(self, task_id: str) -> set[WebSocket]:
        return self._connections[task_id]

    async def connect(self, task_id: str, ws: WebSocket) -> None:
        self._connections[task_id].add(ws)
        logger.bind(task_id=task_id).debug("WS connected; total={}", len(self._connections[task_id]))

    def disconnect(self, task_id: str, ws: WebSocket) -> None:
        self._connections[task_id].discard(ws)
        if not self._connections[task_id]:
            del self._connections[task_id]
        logger.bind(task_id=task_id).debug("WS disconnected")

    async def broadcast(self, task_id: str, message: dict[str, Any]) -> None:
        """Send JSON message to all connections for task_id; silently drop broken ones."""
        payload = json.dumps(message, ensure_ascii=False)
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(task_id, set())):
            try:
                await ws.send_text(payload)
            except Exception as exc:
                logger.bind(task_id=task_id).warning("WS send failed, removing: {}", exc)
                dead.append(ws)
        for ws in dead:
            self.disconnect(task_id, ws)


# Singleton — shared across routers
ws_manager = WebSocketManager()
```

- [ ] **Step 4: 运行测试确认全部 PASS**

```bash
pytest tests/test_ws_manager.py -v
```

期望：6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ws_manager.py backend/tests/test_ws_manager.py
git commit -m "feat(ws): add WebSocketManager with connect/disconnect/broadcast"
```

---

## Task 2: 心跳机制（30s ping / 60s 超时断开）

**Files:**
- Modify: `backend/app/services/ws_manager.py` — 新增 `run_heartbeat()` 方法
- Modify: `backend/tests/test_ws_manager.py` — 新增心跳测试

- [ ] **Step 1: 写失败测试 — 心跳 ping 发送**

```python
# 追加到 backend/tests/test_ws_manager.py

@pytest.mark.asyncio
async def test_heartbeat_sends_ping(manager, mock_ws):
    """Heartbeat must send {type: ping} within the first interval."""
    task_id = "task-hb"
    await manager.connect(task_id, mock_ws)
    # Run heartbeat with short intervals for testing
    task = asyncio.create_task(
        manager.run_heartbeat(mock_ws, task_id, ping_interval=0.05, timeout=0.2)
    )
    await asyncio.sleep(0.1)  # wait for at least one ping
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # Verify ping was sent
    calls = [call.args[0] for call in mock_ws.send_text.await_args_list]
    assert any('"ping"' in c for c in calls)


@pytest.mark.asyncio
async def test_heartbeat_disconnects_on_timeout(manager):
    """If no pong received within timeout, ws.close() must be called."""
    task_id = "task-timeout"
    ws = MagicMock()
    ws.send_text = AsyncMock()
    ws.close = AsyncMock()
    await manager.connect(task_id, ws)
    # ping_interval=0.05s, timeout=0.1s — timeout fires quickly
    await manager.run_heartbeat(ws, task_id, ping_interval=0.05, timeout=0.1)
    ws.close.assert_awaited_once()
```

- [ ] **Step 2: 运行测试确认 FAIL**

```bash
pytest tests/test_ws_manager.py::test_heartbeat_sends_ping tests/test_ws_manager.py::test_heartbeat_disconnects_on_timeout -v
```

期望：`AttributeError: 'WebSocketManager' object has no attribute 'run_heartbeat'`

- [ ] **Step 3: 实现 run_heartbeat（GREEN）**

在 `ws_manager.py` 的 `WebSocketManager` 类中追加：

```python
    def record_pong(self, ws: WebSocket) -> None:
        """Called by the route handler when a pong message is received."""
        self._pong_received.add(id(ws))

    async def run_heartbeat(
        self,
        ws: WebSocket,
        task_id: str,
        ping_interval: float = 30.0,
        timeout: float = 60.0,
    ) -> None:
        """Send ping every ping_interval seconds; close connection if no pong within timeout."""
        self._pong_received: set[int]  # declared on __init__ too — see below
        while True:
            await asyncio.sleep(ping_interval)
            self._pong_received.discard(id(ws))
            try:
                await ws.send_text(json.dumps({"type": "ping"}))
            except Exception:
                self.disconnect(task_id, ws)
                return
            # Wait up to (timeout - ping_interval) for pong
            deadline = timeout - ping_interval
            waited = 0.0
            step = 0.05
            while waited < deadline:
                if id(ws) in self._pong_received:
                    break
                await asyncio.sleep(step)
                waited += step
            else:
                logger.bind(task_id=task_id).warning("WS heartbeat timeout, closing")
                self.disconnect(task_id, ws)
                await ws.close()
                return
```

同时在 `__init__` 中添加：
```python
        self._pong_received: set[int] = set()
```

- [ ] **Step 4: 运行全部测试确认 PASS（含旧测试无回归）**

```bash
pytest tests/test_ws_manager.py -v
```

期望：8 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ws_manager.py backend/tests/test_ws_manager.py
git commit -m "feat(ws): add heartbeat with 30s ping / 60s timeout"
```

---

## Task 3: WebSocket 路由端点（鉴权 + 生命周期）

**Files:**
- Modify: `backend/app/routers/ws.py` — 实现 `/ws/task/{task_id}` 端点
- Create: `backend/tests/test_ws_endpoint.py` — 端点集成测试

- [ ] **Step 1: 写失败测试 — 端点基础行为**

```python
# backend/tests/test_ws_endpoint.py
"""WebSocket 端点集成测试"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_ws_rejects_unknown_task(client):
    """Connecting to a non-existent task_id must result in HTTP 404 before upgrade."""
    with patch("app.routers.ws.get_task_exists", new_callable=AsyncMock, return_value=False):
        with pytest.raises(Exception):  # 404 before WS upgrade
            with client.websocket_connect("/ws/task/nonexistent-task"):
                pass


def test_ws_accepts_known_task(client):
    """Connecting to a known task_id should succeed and receive the 'connected' message."""
    with patch("app.routers.ws.get_task_exists", new_callable=AsyncMock, return_value=True):
        with patch("app.routers.ws.ws_manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = MagicMock()
            mock_mgr.run_heartbeat = AsyncMock()
            with client.websocket_connect("/ws/task/task-001") as ws:
                data = ws.receive_json()
                assert data["type"] == "connected"
                assert data["task_id"] == "task-001"


def test_ws_pong_handled(client):
    """Sending {type: pong} must call ws_manager.record_pong."""
    with patch("app.routers.ws.get_task_exists", new_callable=AsyncMock, return_value=True):
        with patch("app.routers.ws.ws_manager") as mock_mgr:
            mock_mgr.connect = AsyncMock()
            mock_mgr.disconnect = MagicMock()
            mock_mgr.record_pong = MagicMock()
            mock_mgr.run_heartbeat = AsyncMock()
            with client.websocket_connect("/ws/task/task-001") as ws:
                ws.receive_json()  # consume 'connected'
                ws.send_json({"type": "pong"})
                # Give event loop a tick to process
                import time; time.sleep(0.05)
            mock_mgr.record_pong.assert_called_once()
```

- [ ] **Step 2: 运行测试确认 FAIL**

```bash
pytest tests/test_ws_endpoint.py -v
```

期望：导入错误或连接被拒绝（ws.py 是空壳）

- [ ] **Step 3: 实现 ws.py 端点（GREEN）**

```python
# backend/app/routers/ws.py
"""WebSocket 路由 — /ws/task/{task_id}"""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.task import Task
from app.services.ws_manager import ws_manager
from app.utils.logger import logger

router = APIRouter(tags=["websocket"])


async def get_task_exists(task_id: str, session: AsyncSession) -> bool:
    result = await session.get(Task, task_id)
    return result is not None


@router.websocket("/ws/task/{task_id}")
async def websocket_task(task_id: str, websocket: WebSocket):
    async for session in get_session():
        exists = await get_task_exists(task_id, session)
        break
    if not exists:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    await ws_manager.connect(task_id, websocket)
    log = logger.bind(task_id=task_id)
    log.info("WS client connected")
    await websocket.send_text(json.dumps({"type": "connected", "task_id": task_id}))
    heartbeat_task = asyncio.create_task(
        ws_manager.run_heartbeat(websocket, task_id)
    )
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "pong":
                ws_manager.record_pong(websocket)
    except WebSocketDisconnect:
        log.info("WS client disconnected")
    finally:
        heartbeat_task.cancel()
        ws_manager.disconnect(task_id, websocket)

- [ ] **Step 4: 运行测试确认 PASS**

```bash
pytest tests/test_ws_endpoint.py -v
```

期望：3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/ws.py backend/tests/test_ws_endpoint.py
git commit -m "feat(ws): implement /ws/task/{task_id} endpoint with auth and heartbeat"
```

---

## Task 4: 全量测试 + 无回归验证

**Files:** 无新增

- [ ] **Step 1: 运行全量非 DB 测试，确认无回归**

```bash
cd backend
pytest tests/ -v --ignore=tests/test_task_api.py --ignore=tests/test_agent_core.py -k "not db"
```

期望：新增 ~11 tests（ws_manager 8 + ws_endpoint 3），旧 129 tests 全绿，共 ≥140 passed

- [ ] **Step 2: 检查 ws_router 已注册到 main.py**

确认 `backend/app/routers/__init__.py` 导出 `ws_router`，`main.py` 已 `include_router(ws_router)`。
（已在现有代码中完成，无需修改）

- [ ] **Step 3: 更新 progress.md**

在 `docs/progress.md` 顶部添加：

```markdown
## Step 5.1 WebSocket 后端基础设施（2026-03-24）
- 新增 `app/services/ws_manager.py`：WebSocketManager（connect/disconnect/broadcast/heartbeat/record_pong）
- 新增 `app/routers/ws.py`：`/ws/task/{task_id}` WebSocket 端点，握手鉴权（task_id 不存在关闭连接），应用层心跳 30s ping / 60s 超时断开
- 新增 `tests/test_ws_manager.py`：8 单元测试
- 新增 `tests/test_ws_endpoint.py`：3 集成测试
- 全量测试：≥140 passed，0 new failures
```

- [ ] **Step 4: 更新 IMPLEMENTATION_PLAN.md Step 5.1 所有 `- [ ]` → `- [x]`**

- [ ] **Step 5: Final commit**

```bash
git add docs/progress.md docs/IMPLEMENTATION_PLAN.md
git commit -m "docs: mark Step 5.1 complete"
```

---

## 验收标准

- `WebSocketManager` 单元测试 8 个全绿
- WebSocket 端点集成测试 3 个全绿  
- 全量测试无回归（≥140 passed）
- 已注册 ws_router 到 FastAPI app
- 握手鉴权：task_id 不存在时连接被关闭
- 应用层心跳：30s ping，60s 无 pong 断开
