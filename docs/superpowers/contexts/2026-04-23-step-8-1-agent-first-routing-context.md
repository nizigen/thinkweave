# Step 8.1 Agent-First Routing Context

**Date:** 2026-04-23  
**Status:** Ready for planning  
**Source:** GSD discuss-phase (manual fallback, no gsd binary in current env)

## Phase Boundary

本阶段只解决一个问题：
- 让“用户创建 Agent”直接参与任务分配决策，避免系统继续表现为固定角色流水线。

本阶段不做：
- 新增业务能力（如评论、检索、导出等）
- 重写长文本 FSM
- 更换底层消息总线（Redis Streams 保持不变）

## Current-State Findings (Code-Backed)

1. DAG 角色被严格限制为固定集合：`outline/writer/reviewer/consistency`。  
   - `backend/app/schemas/task.py` 的 `VALID_AGENT_ROLES` 与 `DAGNodeSchema.role` 校验决定了分解结果只能落在固定角色。
2. 分解服务默认依赖固定角色契约。  
   - `backend/app/services/task_decomposer.py` 要求首节点必须是 `outline`。
3. 调度器按“角色 + idle”匹配，无法表达 capability/策略约束。  
   - `backend/app/services/dag_scheduler.py::_match_agent()` 仅 `Agent.status == idle` + `Agent.role == node.role`。
4. 创建任务时虽记录 `routing_snapshot`，但只是观测数据，不参与路由策略。  
   - `backend/app/services/task_service.py::_build_routing_snapshot()`。

结论：当前实现里“创建 Agent”的价值主要体现在同角色的水平扩容，而非“按用户定义能力动态派发”。

## Locked Decisions

1. 路由优先级改为三层：
   - 显式绑定优先：节点指定 `assigned_agent_id` 时必须命中。
   - 能力匹配优先：节点声明 `required_capabilities` 时优先按能力匹配。
   - 角色兜底：能力不全时回退到角色匹配（保持兼容）。
2. 保持现有角色语义，但从“唯一匹配键”降级为“兼容字段”。
3. DAG 节点契约扩展：允许表达 `required_capabilities`、`routing_mode`、`preferred_agents`。
4. 增加可解释路由：每次分配记录 `routing_reason`（例如 `explicit_bind` / `capability_match` / `role_fallback`）。
5. API 兼容策略：旧请求不带新字段时，行为与现网一致。

## the agent's Discretion

1. capability 匹配算法细节（是否引入权重、阈值、排序打分）。
2. `preferred_agents` 的冲突处理（不可用时是否降级、是否强制失败）。
3. `routing_reason` 的存储位置（`checkpoint_data` vs 节点字段）。
4. 前端展示粒度（任务详情页 vs 监控页）。

## Specific UX/Behavior Ideas

1. 创建任务后立即返回“路由可行性预检”：
   - required capabilities
   - matched agents
   - fallback 路径
   - missing capabilities
2. 监控页节点详情展示“为何分配给该 Agent”。

## Deferred Ideas

1. 完全去角色化（只保留 capability）暂缓，避免一次性破坏长文本流程契约。
2. 自动创建临时 Agent（按任务需求临时注册）暂缓到后续 phase。
3. 多目标路由（成本/时延/质量优化）暂缓。

## Acceptance Signal for This Phase

满足以下条件即认为本阶段目标达成：
- 新建 Agent 的能力配置会影响节点最终分配结果。
- 不配置能力字段时，旧任务流程不回归。
- 路由原因可追踪、可在 API 层读到。
