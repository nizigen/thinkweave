# Step 5 WebSocket Bridge Design

## Scope

本设计覆盖 Phase 5 的后端实时链路收口：

- 验收并补漏 `Step 5.1 WebSocket 后端基础设施`
- 实现 `Step 5.2 Redis -> WebSocket 事件桥接`

不包含前端 hook、DAG 可视化和监控面板组件，这些仍归后续 `Step 5.4` - `Step 5.6`。

## Current State

- `backend/app/routers/ws.py` 已存在，并已注册到 `backend/app/main.py`
- `backend/app/services/ws_manager.py` 已存在，具备 connect / disconnect / broadcast / heartbeat
- `backend/tests/test_ws_endpoint.py` 与 `backend/tests/test_ws_manager.py` 已存在
- Redis 任务事件流已通过 `task:{task_id}:events` 写入，`communicator.py` 中已有 `send_status_update()` / `consume_task_events()` 等能力
- 缺口是没有共享事件桥接层把 Redis task event 自动转发给当前在线的 WebSocket 订阅者

## Goals

1. 保持现有 WebSocket 握手、鉴权、心跳模型不倒退
2. 为每个 `task_id` 启动最多一个桥接协程，避免多客户端重复消费同一条 Redis event
3. 桥接层输出统一的前端事件结构，优先兼容现有 `status_update`，为后续 `node_update` / `dag_update` / `chapter_preview` 等类型留好接口
4. 在没有订阅连接时自动停桥，避免后台悬挂协程

## Approaches Considered

### Approach A: 每个 WebSocket 连接单独读 Redis

- 优点：实现最直接
- 缺点：同一任务多连接会重复读取、重复广播，生命周期难控，不适合实时监控面板

### Approach B: 每个 task 一个共享桥接协程

- 优点：和 `WebSocketManager` 的 `task_id -> connections` 模型一致；多客户端共享一个 Redis reader；方便做首连启动、断完停桥
- 缺点：需要额外维护桥接任务注册表

### Approach C: 放弃桥接，仅靠前端轮询 REST

- 优点：实现最省
- 缺点：不满足 phase5“实时监控 + WebSocket”的目标

## Chosen Design

采用 Approach B。

### Component Boundaries

- `backend/app/routers/ws.py`
  - 保持只做握手、鉴权、连接注册、心跳和断开清理
  - 在连接建立后调用 `event_bridge.ensure_started(task_id)`
  - 在连接断开后，如果该任务已无连接，调用 `event_bridge.stop(task_id)`

- `backend/app/services/ws_manager.py`
  - 继续维护连接集合与心跳
  - 不直接感知 Redis，避免把连接管理和桥接读取耦死

- `backend/app/services/event_bridge.py`
  - 新增 `TaskEventBridge`
  - 维护 `task_id -> asyncio.Task`
  - 只允许每个任务存在一个 reader 协程
  - 使用 `xread_latest()` 从 `task:{task_id}:events` 只读拉取最新事件
  - 将 Redis `MessageEnvelope` 规范化为前端消息后调用 `ws_manager.broadcast()`

- `backend/app/schemas/ws_event.py`
  - 定义统一 WebSocket 事件模型
  - 当前至少覆盖：
    - `connected`
    - `node_update`
    - `log`
    - `task_done`
    - `chapter_preview`
    - `review_score`
    - `consistency_result`
    - `dag_update`
  - 同时兼容现有 Redis `status_update`，在桥接层映射为 `node_update`

### Event Normalization

桥接后对前端暴露统一结构：

- `type`
- `task_id`
- `node_id`
- `from_agent`
- `timestamp`
- `payload`

映射策略：

- `status_update` -> `node_update`
- 其他已在白名单内的类型直接透传
- 未知类型默认丢弃并记录 warning，避免脏事件污染前端协议

### Lifecycle

1. WebSocket 握手成功
2. `ws_manager.connect(task_id, ws)`
3. `event_bridge.ensure_started(task_id)` 幂等启动桥接
4. 桥接循环持续从 Redis 读取并广播
5. WebSocket 断开
6. `ws_manager.disconnect(task_id, ws)`
7. 若 `ws_manager` 中该任务连接数为 0，则 `event_bridge.stop(task_id)`

### Error Handling

- Redis 读失败：记录异常，短暂 sleep 后重试；若桥接被显式停止则退出
- 广播失败：交给 `ws_manager.broadcast()` 清理坏连接
- 未知事件类型：warning + 丢弃
- 任务无连接：桥接退出并从注册表移除

## Testing Strategy

### Step 5.1 Closeout

- 复跑 `test_ws_manager.py`
- 复跑 `test_ws_endpoint.py`
- 确认 ws router 已注册

### Step 5.2 Bridge

- 新增 `backend/tests/test_event_bridge.py`
- 覆盖：
  - `ensure_started()` 幂等，不重复创建 reader
  - Redis `status_update` 被映射为 `node_update`
  - 已知事件被广播到 `ws_manager.broadcast()`
  - 未知事件被忽略
  - 任务无连接时 reader 自动退出
  - `stop()` 能取消桥接并清理注册表

## Risks

- 当前仓库工作树较脏，修改时必须避免覆盖用户已有未提交改动
- WebSocket 当前使用 query token，而 REST 使用 Bearer token；这一差异先保留，不在本次后端桥接任务里改协议
- `Step 5.3` 事件发射尚未完成，因此桥接层先以兼容现有 `status_update` 为主，后续再扩充生产者
