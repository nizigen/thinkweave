# ThinkWeave ROADMAP (Locked By User)

## 重构目标（新版）
- 保留：前端页面、Agent 管理、任务编排监控、DAG 可视化。
- 重写：后端生成链路（语义 stage）、schema 契约、repair 闭环、质量 gate。
- 可直接参考：`/root/github/konrunsgpt/app/services/pipeline.py` 与 `docs/report_pipeline.md`（按 ThinkWeave 数据模型适配）。

## 全局执行约束（强制）
1. 本里程碑一律按**全量重构**执行，不做旧链路上的增量修补。
2. 后端 `app/` 与相关服务模块视为 clean-room 区域，允许直接替换，不要求兼容旧实现细节。
3. 若出现“在旧代码上补丁式推进”倾向，必须回退到重写路径并更新计划。
4. 每个 Phase 的 deliverables 默认针对“新链路实现”，不是“旧链路加功能”。

## Phase 1 - Stage 骨架 + Schema 契约层
目标：建立全新语义 stage 主线与统一 schema 契约底座（clean-room）。

Deliverables:
1. 语义 stage contract 定义与 role 映射
2. DAG payload 注入 `stage_code` / `schema_version` / `stage_contract`
3. 核心节点 schema 校验机制（orchestrator/writer/reviewer/consistency）

## Phase 2 - Research/Outline/Section/Review/Consistency 全链路重写
目标：按 research-first 全量重写主生成链路（替换旧后端链路）。

Deliverables:
1. Research -> Outline -> Section Writer -> Reviewer -> Consistency 串联
2. 检索与去重策略对齐 KonrunsGPT
3. 证据池与章节边界约束稳定化

## Phase 3 - Repair DAG + Final Polish + Quality Gate
目标：在新链路上落地 repair 闭环与终稿质量门，不依赖旧 runtime。

Deliverables:
1. consistency `repair_targets` -> 定向修复 DAG 注入
2. Final polish 阶段（跨章节整合、风格统一、字数收敛）
3. 质量 gate（字数、结构、证据、冲突）

## Phase 4 - Web 监控对齐（Stage 可视化）+ E2E 验证
目标：前后端观测口径与新链路一致，并用真实流程验收。

Deliverables:
1. 监控页展示 stage 语义与 DAG 节点状态
2. 失败原因、重试轨迹、修复波次可视化
3. Playwright 端到端验证与日志回放
