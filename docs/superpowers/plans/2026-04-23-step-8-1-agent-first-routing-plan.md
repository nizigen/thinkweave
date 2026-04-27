# Step 8.1 Agent-First Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` or `superpowers:executing-plans`.

**Goal:** 把任务分配从“固定 role 流程”升级为“用户定义 agent 能力驱动 + role 兼容兜底”的可解释路由。

**Architecture:** 在不破坏现有 FSM / Redis / DAG 执行链的前提下，扩展 DAG 节点路由元数据与调度器匹配策略。调度顺序：`explicit_bind -> capability_match -> role_fallback`。

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, pytest/pytest-asyncio

---

## Task 1: 扩展 DAG 节点路由契约（Schema + Validation）

**Files:**
- Modify: `backend/app/schemas/task.py`
- Modify: `backend/app/services/task_decomposer.py`
- Modify: `backend/tests/test_task_decomposer.py`

- [x] Step 1: 为 `DAGNodeSchema` 增加可选字段：
  - `required_capabilities: list[str] = []`
  - `preferred_agents: list[str] = []`（Agent 名称或 ID 字符串，后续解析）
  - `routing_mode: Literal["auto", "capability_first", "strict_bind"] = "auto"`
- [x] Step 2: 保留 `role` 字段但允许缺省（为后续 capability-only 预留）。
- [x] Step 3: 在 `parse_dag_response` 中加入新增字段校验和向后兼容测试。
- [x] Step 4: 测试覆盖：
  - 旧 DAG JSON（仅 role）仍可通过。
  - 新 DAG JSON（capability + preferred_agents）通过。
  - `strict_bind` 且无可用 agent 时返回结构化验证错误。

**Checkpoint:** `pytest backend/tests/test_task_decomposer.py -q`

---

## Task 2: 调度器实现三层路由策略

**Files:**
- Modify: `backend/app/services/dag_scheduler.py`
- Modify: `backend/app/models/task_node.py`（如需新增字段）
- Modify: `backend/tests/test_dag_scheduler.py`

- [x] Step 1: 拆分 `_match_agent()` 为可解释策略：
  - `_match_explicit_agent()`
  - `_match_by_capabilities()`
  - `_match_by_role_fallback()`
- [x] Step 2: 在 `_assign_node()` 前生成 `routing_reason`，并写入节点运行上下文（或 checkpoint_data.control.preview_cache）。
- [x] Step 3: capability 匹配最小规则：
  - agent 必须 `idle`
  - agent `capabilities` 覆盖节点 `required_capabilities`
  - 多候选时按 `created_at` 稳定排序
- [x] Step 4: `routing_mode` 行为：
  - `auto`: capability 优先，失败回退 role
  - `capability_first`: 与 `auto` 同，但必须先尝试 capability
  - `strict_bind`: 仅允许 `preferred_agents` / `assigned_agent_id` 命中
- [x] Step 5: 测试覆盖：
  - capability 命中优先于 role-only agent
  - capability 不满足时 role fallback 生效
  - strict_bind 无匹配时节点保留 ready 并记录原因

**Checkpoint:** `pytest backend/tests/test_dag_scheduler.py -q`

---

## Task 3: 任务创建阶段输出路由预检

**Files:**
- Modify: `backend/app/services/task_service.py`
- Modify: `backend/app/schemas/task.py`
- Modify: `backend/tests/test_task_api.py`

- [x] Step 1: 扩展 `routing_snapshot`：
  - `required_capabilities`
  - `available_capabilities`
  - `missing_capabilities`
  - `strict_bind_failures`
- [x] Step 2: 将 `routing_snapshot` 透传到 `TaskDetailRead`（保持现字段兼容）。
- [x] Step 3: API 回归测试：
  - 旧任务创建请求返回结构不破坏。
  - 新字段存在时可读且值正确。

**Checkpoint:** `pytest backend/tests/test_task_api.py -q`

---

## Task 4: Agent 侧能力声明规范化

**Files:**
- Modify: `backend/app/schemas/agent.py`
- Modify: `backend/app/services/agent_manager.py`
- Modify: `backend/tests/test_agents.py`

- [x] Step 1: 确保 Agent `capabilities` 字段标准化（去空白、去重、大小写策略一致）。
- [x] Step 2: 对 role preset 给出默认 capability 基线（不改变现有 role）。
- [x] Step 3: 增加校验，拒绝非法 capability token（空字符串、超长）。

**Checkpoint:** `pytest backend/tests/test_agents.py -q`

---

## Task 5: 可观测性与回归验证

**Files:**
- Modify: `backend/tests/test_fault_recovery.py`
- Modify: `backend/tests/test_communicator.py`
- Optional: `frontend/src/pages/Monitor.tsx`（若本阶段包含展示）

- [x] Step 1: 日志/事件中增加路由标签：`routing_reason`, `routing_mode`。
- [x] Step 2: 核心回归套跑（至少包含调度、task api、agent api）。
- [x] Step 3: 文档更新（`docs/progress.md` + 本计划的完成勾选）。

**Checkpoint:**
- `pytest backend/tests/test_dag_scheduler.py backend/tests/test_task_api.py backend/tests/test_agents.py -q`

---

## Risks & Mitigations

1. 风险：能力匹配引入后出现“节点长期 ready 不被分配”。  
   缓解：保留 role fallback，`strict_bind` 仅在显式模式启用。
2. 风险：旧 DAG 数据缺少新字段。  
   缓解：所有新字段默认可选并提供兼容默认值。
3. 风险：路由解释信息写入位置不一致。  
   缓解：先统一写入 `checkpoint_data.routing`，后续再抽成独立表。

## Definition of Done

- [x] 新建 Agent 的 capability 能影响调度结果。
- [x] 旧任务链路（无 capability）行为不变。
- [x] API 能返回可解释路由证据。
- [x] 关键调度与任务测试通过。
