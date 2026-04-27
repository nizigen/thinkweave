# Phase 1: Schema & Stage Contracts - Context

**Gathered:** 2026-04-25
**Status:** Ready for planning (restarted)

<domain>
## Phase Boundary

在保留现有 Web UI（任务创建、Agent 管理、任务监控）的前提下，重构后端长文生成主链路为“阶段主线 + 严格 schema 契约 + 可修复闭环”的架构。

</domain>

<decisions>
## Implementation Decisions

### 重构范围
- **D-01:** Phase 1 按“全量重构核心链路”执行，旧逻辑仅作为参考资产。
- **D-02:** 前端页面结构与交互入口保持兼容，不做本阶段视觉重构。

### 流程语义
- **D-03:** 采用语义化阶段主线（`SCOPING`, `RESEARCH`, `OUTLINE`, `DRAFT`, `REVIEW`, `ASSEMBLY`, `QA`）。
- **D-04:** DAG 作为阶段内执行图，不再单独承载业务全语义。

### Schema 与质量门
- **D-05:** orchestrator / writer / reviewer / consistency 全部执行结构化 schema 校验。
- **D-06:** schema 校验失败不可静默降级，必须重试并记录失败原因。
- **D-07:** 标题约束为最多二级（`#`/`##`），禁止三级标题。

### 修复策略
- **D-08:** consistency `pass=false` 时优先按 `repair_targets` 注入定向修复子图。
- **D-09:** 字数不足触发补写波次，达到上限后失败并输出 `error_message`。

### the agent's Discretion
- 修复波次上限、章节批大小、重试退避策略。
- 阶段日志字段的具体命名（在不破坏兼容性的前提下）。

</decisions>

<specifics>
## Specific Ideas

- 参考 KonrunsGPT 的调研与撰写链路：先研究再写作，不让 writer 在无证据上下文中直接扩写。
- 参考 KonrunsGPT 的 prompt 约束风格：明确输入输出 schema、失败条件、禁止项。

</specifics>

<canonical_refs>
## Canonical References

### 项目与范围
- `.planning/PROJECT.md` — 项目愿景、范围锁定、成功标准。
- `.planning/REQUIREMENTS.md` — Phase 1 需要满足的契约与质量要求。
- `.planning/ROADMAP.md` — 当前里程碑阶段定义与边界。

### 参考实现
- `/root/github/konrunsgpt/docs/report_pipeline.md` — 分阶段报告生成链路与质量纪律。

### 现有代码入口
- `backend/app/services/task_service.py` — 任务创建入口与编排路由。
- `backend/app/services/pipeline_orchestrator.py` — 新阶段主线编排骨架。
- `backend/app/services/stage_contracts.py` — 语义化阶段契约与 schema 版本注入。
- `backend/app/services/dag_scheduler.py` — DAG 节点调度、修复注入、补写波次逻辑。

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `stage_contracts.py`: 已提供阶段编码、契约描述、schema_version。
- `pipeline_orchestrator.py`: 已提供任务主线计划入口，可继续扩展阶段推进。
- `dag_scheduler.py`: 已具备 `repair_targets` 注入和补写波次基础逻辑。

### Established Patterns
- 后端通过任务状态与 checkpoint 存储流程元数据。
- 前端监控页面基于 DAG 节点和 websocket 事件更新。

### Integration Points
- 任务入口在 `task_service.create_task()`。
- 阶段元数据需贯穿 scheduler payload、日志与结果导出。

</code_context>

<deferred>
## Deferred Ideas

- 新增外部检索 connector（X/Reddit 等）作为后续阶段处理。
- 大规模 UI 视觉重做不纳入本阶段。

</deferred>

---

*Phase: phase-1*
*Context gathered: 2026-04-25*
