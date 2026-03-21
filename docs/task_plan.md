# task_plan.md — 任务路线图

## 项目目标

构建层级化多Agent协作编排平台，核心验证：万字长文本生成（技术报告/小说），并行章节内容重复率 < 5%。

---

## 阶段总览

| Phase | 名称 | 状态 | 完成日期 |
|-------|------|------|---------|
| 0 | 项目脚手架 | ✅ 完成 | 2026-03-06 |
| 1 | Agent管理模块 | ✅ 完成 | 2026-03-07 |
| 2 | 任务分解引擎 | ✅ 完成 | 2026-03-09 |
| 3 | DAG调度引擎 | ✅ 完成 (3.1-3.3) | 2026-03-09 |
| 4 | 长文本控制 + 记忆层 | 🔜 下一步 | — |
| 5 | 实时监控 + WebSocket | 待开始 | — |
| 6 | 结果展示 + 导出 | 待开始 | — |
| 7 | 系统集成测试 | 待开始 | — |

---

## Phase 4 详细路线（当前焦点）

```
Step 4.1   长文本FSM（状态机+检查点+崩溃恢复）
Step 4.1a  cognee vendor spike（2-4h，验证依赖链，锁定版本）
Step 4.1b  记忆层基础设施（Neo4j/Qdrant Docker + vendor模块 + SessionMemory + 单元测试）
Step 4.2   专用Agent实现 + 记忆集成（Outline/Writer/Reviewer/Consistency + MemoryMiddleware）
Step 4.3   长文本生成流程集成 + 记忆生命周期 + 重复率度量
Step 4.4   Knowledge Graph（跨任务知识积累 + Session→KG promote）
```

**推荐执行顺序**：4.1 → 4.1a → 4.1b → 4.2 → 4.3 → 4.4

4.1a (cognee spike) 可与 4.1 (FSM) **并行**——FSM 不依赖记忆层，spike 不依赖 FSM。

---

## 关键决策记录

| 日期 | 决策 | 结论 |
|------|------|------|
| 2026-03-06 | 写作模式 | 并行，非串行。Chain-of-Agents 思想体现在大纲 context bridges |
| 2026-03-07 | LLM 调用方式 | llm_client.py 统一适配层，禁止直接 import openai |
| 2026-03-07 | 上下文管理 | 三层记忆（Working/Task/Persistent）+ 渐进式披露 |
| 2026-03-18 | 记忆层框架 | vendor cognee 核心 ~500-800 LOC，不 pip install 整包 |
| 2026-03-18 | 去重策略 | 四级级联：大纲领地→写前上下文→写后检测→审查兜底 |
| 2026-03-18 | pgvector vs Qdrant | 分离：pgvector 管 RAG，Qdrant 管记忆去重 |
| 2026-03-18 | 中间件顺序 | ContextSummary 在 Memory 之前（先压缩旧，再注入新） |

---

## 已知风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| cognee vendor 依赖链过深 | Step 4.1b 延期 | Step 4.1a spike 先验证；降级方案：不用 cognify()，自研实体提取 |
| 并行 Writer 内容重复 | 报告质量差 | 四级去重；度量脚本验证 |
| Neo4j/Qdrant 增加部署复杂度 | 运维成本 | Graceful degradation 到 InMemory；MEMORY_ENABLED=false 一键关闭 |
| Token 预算不够完成 Stage 2+3 | 跳过审查 | 当前步骤做完就停，下次会话从 Stage 3 恢复 |

## 2026-03-21 Runtime Integration Update
- Completed: API-level `agent_config` storage + runtime consumption for model/max_tokens/temperature.
- Completed in this lane: bound `max_retries` and `fallback_models` into llm_client retry/fallback orchestration (runtime payload -> resolve_llm_call_params -> llm_client/decompose_task).

## 2026-03-21 Prompt & Injection Execution
- In progress: implement stage-aware skill injection and prompt hardening in code.
- Done this round: middleware integration + prompt schema upgrades + unit test expansion.
- Next: add FSM integrity gates (pre_review_integrity / final_integrity) and mid-entry detector.

## 2026-03-21 Step 4.2 Execution Checklist (Runtime Retry/Fallback)
- [x] Dispatch payload carries `model` and `agent_config`.
- [x] Runtime resolver extracts `max_retries` and `fallback_models`.
- [x] Worker/Manager/Orchestrator pass through resolved LLM params.
- [x] Decomposer path passes retry/fallback overrides to `chat_json`.
- [x] `llm_client` retry/fallback orchestrator consumes overrides.
- [x] Tests cover propagation + fallback chain behavior.

## 2026-03-21 Addendum (Step 4.3D Mid-Entry Detector)
- [x] Added entry-stage detector from user materials (`draft_text`, `review_comments`) in `app/services/entry_stage.py`.
- [x] Wired task bootstrap to detected stage: `task_service.create_task` now sets `tasks.fsm_state` and stores `entry_stage` + input flags in `checkpoint_data`.
- [x] Enforced integrity-first mid-entry policy: any mid-entry material routes to `pre_review_integrity`.
- [x] Added auto stage inference to `StageSkillInjectionMiddleware` when no explicit stage/fsm_state is provided.
- [x] Added tests for detector + middleware inference + API payload scenarios.
- [ ] Pending environment verification: rerun full `test_task_api.py` when PostgreSQL test DB is reachable.

## 2026-03-21 Addendum (Step 4.3B/4.3E Prompt Contracts)
- [x] Added claim-level integrity prompt: `backend/prompts/consistency/check_claims.md`.
- [x] Added prompt contract tests for reviewer/revise/consistency (`backend/tests/test_prompt_contracts.py`).
- [x] Fixed unescaped JSON braces in prompt templates to prevent runtime `format_map` KeyError.
- [x] Verified with prompt-related test suite: 16 tests passed.

## 2026-03-21 Addendum (Step 4.3C Observability Trace)
- [x] Persisted stage skill injection trace to runtime logs in `backend/app/agents/base_agent.py`.
- [x] Added regression test in `backend/tests/test_agent_core.py`.
- [x] Targeted stage-skill middleware test group passes.

## 2026-03-21 Addendum (Step 4.3A Checkpoint Policy)
- [x] Implemented `CheckpointPolicy` (FULL/SLIM/MANDATORY) in long-text FSM.
- [x] Added unit tests for policy payload behavior.
- [x] Non-DB verification passed for policy subset.
- [ ] Pending full DB-backed FSM regression when PostgreSQL test service is stable.
