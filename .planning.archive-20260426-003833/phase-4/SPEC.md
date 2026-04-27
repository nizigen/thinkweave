# Phase 4 SPEC (Locked)

## Goal
完成 Web 监控对齐（stage 可视化）并通过真实环境 E2E 验证。

## Mode
对齐全量重构后的新后端链路进行观测与验收，不以旧链路结果作为验收对象。

## Requirements
1. 监控页展示语义 stage 与 DAG 节点状态对齐。
2. 展示修复波次、重试原因、失败原因链路。
3. 提供 Playwright 全流程验证脚本与日志摘要。

## Acceptance
1. 监控页面能区分 stage 进度与节点进度。
2. 至少两条真实题目任务有可复现 E2E 记录。
3. 失败样本可快速定位问题 gate 与节点。
