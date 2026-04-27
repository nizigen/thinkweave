# Phase 1 SPEC (Locked)

## Goal
完成语义 stage 骨架与 schema 契约层，作为后续全链路重写底座。

## Mode
全量重构（clean-room），不允许在旧后端实现上做补丁式改造。

## Requirements
1. 定义语义阶段契约与 role->stage 映射。
2. 任务分解后每个 DAG 节点必须注入 stage 元数据。
3. 完成关键节点 schema 校验入口（orchestrator/writer/reviewer/consistency）。
4. DAG 执行层在新实现中保持语义一致，不依赖旧 runtime 代码路径。

## Acceptance
1. 新任务可看到语义 stage 元数据。
2. schema 违规节点会被拦截并给出失败原因。
3. API 可返回节点 stage 信息。
