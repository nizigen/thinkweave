# Phase 1 PLAN (Restarted)

## Planning Basis
- Source spec: `.planning/phase-1/SPEC.md`
- Locked context: `.planning/phase-1/1-CONTEXT.md`
- Execution model: 阶段语义主线 + DAG 执行层（保留）

## Wave 1 - Stage Contract Foundation

## Wave Goal
建立语义阶段契约与入口编排骨架，不破坏现有 DAG 任务分解。

## Tasks
1. 统一阶段码与契约
- 文件：`backend/app/services/stage_contracts.py`
- 动作：确定 `SCOPING/RESEARCH/OUTLINE/DRAFT/REVIEW/ASSEMBLY/QA` 契约结构与 alias 兼容映射。

2. 任务入口阶段化
- 文件：`backend/app/services/pipeline_orchestrator.py`, `backend/app/services/task_service.py`
- 动作：创建任务时仍先分解 DAG，再注入 pipeline 元数据（含 `execution_graph=dag_preserved`）。

3. 节点 payload 注入阶段元数据
- 文件：`backend/app/services/dag_scheduler.py`
- 动作：为节点调用注入 `stage_code` / `stage_contract` / `schema_version`。

## Done Criteria
- 创建任务后可看到 pipeline 阶段元数据。
- DAG 正常初始化，不因阶段化改动中断。
- 旧阶段码历史数据可读（alias 生效）。

## Verification
- 单测：入口阶段元数据注入路径通过。
- 单测：scheduler 关键路径无回归。

## Risks
- 入口重构后，旧测试桩可能仍 patch legacy 符号导致假失败。

## Wave 2 - Schema Gates and Repair Loop

## Wave Goal
把“自由文本容错”改成“结构化硬约束 + 自动修复闭环”。

## Tasks
1. 强化结构化输出 gate
- 文件：`backend/app/agents/worker.py`, `backend/app/services/dag_scheduler.py`
- 动作：writer/reviewer/consistency 输出严格 schema 校验；非法输出触发重试并记录原因。

2. consistency 定向修复注入
- 文件：`backend/app/services/dag_scheduler.py`
- 动作：`pass=false` 且有 `repair_targets` 时，注入修复 writer/reviewer/consistency 子图。

3. 字数补写波次
- 文件：`backend/app/services/dag_scheduler.py`
- 动作：终稿字数不足时注入补写波次，超上限后失败并写明 `error_message`。

4. prompt 契约收紧
- 文件：`backend/prompts/writer/*`, `backend/prompts/reviewer/*`, `backend/prompts/consistency/*`, `backend/prompts/orchestrator/*`
- 动作：对齐 JSON 输出约束、证据链约束、二级标题限制。

## Done Criteria
- consistency 失败不会直接终止，能进入修复波次。
- 低字数不再直接 completed。
- schema 失败具备可追溯重试日志。

## Verification
- 单测：repair 注入路径通过。
- 单测：字数 gate 与补写路径通过。
- 抽样真实任务：可观察修复/补写波次注入。

## Risks
- schema gate 变严后，重试次数上升导致时延增加。

## Wave 3 - Transparency and E2E Closure

## Wave Goal
完成可运维的失败透明化与端到端验收，形成 Phase 1 可收口状态。

## Tasks
1. 失败透明化补齐
- 文件：`backend/app/services/dag_scheduler.py`, `backend/app/schemas/task.py`, `backend/app/routers/ws.py`
- 动作：失败原因、节点重试原因、阶段状态在 API/WS/监控中一致可见。

2. orphan running 恢复强化
- 文件：`backend/app/services/dag_scheduler.py`
- 动作：服务重启后，卡住的 running 节点能安全回收并恢复调度。

3. 全流程真实环境验收
- 文件：`scripts/playwright_cli_real_env.sh`（或新增同类脚本）
- 动作：执行“创建任务 -> 监控 DAG -> 完成/失败解释”全流程，保留日志证据。

## Done Criteria
- 任务终态失败可解释（含 error_message 与原因链）。
- 监控页持续可见 DAG 推进，不出现长期 init 卡死。
- 至少 1 条真实题目任务完成端到端验收记录。

## Verification
- Playwright CLI 跑通关键路径。
- 后端日志可对应到 DAG 节点推进与修复行为。

## Risks
- 外部模型不稳定会影响 E2E 通过率，需要重试策略与日志聚合配套。

## Dependency Order
1. Wave 1 -> 2. Wave 2 -> 3. Wave 3

## Execution Rules
1. 每个 Wave 完成后必须提交：变更清单、测试结果、残余风险。
2. 未达到 Done Criteria 不得进入下一 Wave。
3. 任何临时绕过（降级逻辑）必须在同 Wave 内回收，不得带入下一 Wave。
