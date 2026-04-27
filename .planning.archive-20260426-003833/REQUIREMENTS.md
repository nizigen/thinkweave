# ThinkWeave REQUIREMENTS (Locked By User)

## R1. 语义 Stage 主线（必须）
系统必须采用语义阶段命名：
- DISCOVERY 主题解析与检索计划
- RETRIEVAL 检索与去重
- OUTLINING 提纲生成
- DRAFTING 分章节草稿
- REVIEWING 审查与一致性前置
- VISUALS 图表/图像（可选）
- POLISHING 终稿拼装与润色
- QUALITY 质量校验

## R2. 保留前端与可视化
必须保留现有前端页面、Agent 管理、任务编排监控与 DAG 可视化能力。

## R3. 后端链路重写
后端生成链路必须 clean-room 重写，不可继续沿旧 runtime 增量修补。

## R3.1 执行方式约束（强制）
所有 plan/execution 必须按全量重构推进：
- 不以“在旧链路上补功能”为交付路径。
- 不以“兼容旧实现细节”为优先目标。
- 若发现增量路线，必须立即改回 clean-room 重写路线。

## R4. Schema Contract 强约束
orchestrator/writer/reviewer/consistency 输出必须过 schema gate，违规必须重试或失败。

## R5. Repair 闭环
consistency 失败必须支持 repair_targets 定向修复 DAG 注入。

## R6. 质量 Gate
终态必须通过字数、结构、证据与冲突一致性门槛。
