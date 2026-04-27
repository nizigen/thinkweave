# Phase 2 SPEC (Locked)

## Goal
按 KonrunsGPT 风格重写 Research/Outline/Section/Review/Consistency 全链路。

## Mode
全量重构（clean-room），直接替换旧后端主生成链路，不做增量兼容层。

## Requirements
1. 强制 Research-first：writer 依赖 research 产物。
2. 检索与去重策略按 KonrunsGPT 参考实现适配 ThinkWeave。
3. 章节写作必须带 evidence trace 与边界约束。
4. reviewer 与 consistency 输出必须结构化并可被下游消费。

## Acceptance
1. 单任务可完整跑通 Research->Outline->Writer->Reviewer->Consistency。
2. evidence 与章节映射可追踪。
3. 重复内容与冲突在 consistency 阶段可检出。
