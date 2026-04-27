# Phase 3 SPEC (Locked)

## Goal
实现 repair DAG + final polish + quality gate，形成可修复闭环。

## Mode
全量重构（clean-room）链路上的闭环实现，不在旧逻辑上叠加补丁。

## Requirements
1. consistency `pass=false` 时按 `repair_targets` 注入修复子图。
2. 引入 final polish 阶段（风格统一、跨章整合、篇幅收敛）。
3. 终态质量 gate 联合判定（字数/结构/证据/一致性）。
4. gate 不通过时必须失败且有可解释原因。

## Acceptance
1. 至少一条任务触发 repair 并继续推进。
2. final polish 后输出质量有可观测提升。
3. 失败时 error_message 与节点轨迹可追踪。
