# ThinkWeave PROJECT

## Vision
构建一个可控、可审计、可扩展的多 Agent 长文生成系统：
- 保留 `agentic-nexus` 的 Web 体验（任务创建、Agent 管理、任务编排监控）
- 引入 `KonrunsGPT` 风格的严密 schema 与阶段化约束
- 在长文目标（10k~20k+）下稳定输出结构化、可追溯、低模板化内容

## Product Principles
1. Schema First: 所有关键节点（outline/research/writer/reviewer/consistency）都必须通过结构化输出契约。
2. Stage First: 文章生成必须遵循阶段链路，不允许“直接自由写整篇”。
3. Observable by Default: DAG、节点状态、重试、质量门槛、失败原因均可观测。
4. Human-in-the-loop Ready: 保留提纲确认、回滚重跑、分阶段修复能力。

## Scope Lock (Current Milestone)
- In scope:
  - 保留并增强现有前后端界面与调度框架
  - 重构后端文章生成链路，向 KonrunsGPT 阶段化对齐
  - 强化 schema 对齐、字数达标策略、一致性修复策略
- Out of scope:
  - 大规模 UI 重设计
  - 多租户权限体系重构
  - 外部检索 connector 的大规模新增

## Architecture Baseline
- Source baseline: `/root/github/agentic-nexus`
- Reference implementation: `/root/github/konrunsgpt`
- New workspace: `/root/github/thinkweave`

## Success Criteria
1. 深度任务（target_words=20000）不再出现“低字数 completed”。
2. 节点输出 schema 违规能被自动拦截并重试/修复。
3. 一致性失败、字数不足可触发修复波次，而非直接失败。
4. Web 端可持续看到 DAG 与节点状态推进。
