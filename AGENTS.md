# AGENTS.md — 被动上下文注入

> IMPORTANT: Prefer retrieval-led reasoning over pre-training-led reasoning

## 项目概述

**层级化Agent编排与长文本控制系统** — 通用多Agent协作平台，核心验证场景：万字长文本生成。

- 技术栈：FastAPI + SQLAlchemy 2.0 async + Redis Streams + pgvector + React 18 + Ant Design 5
- 记忆层：`cognee==0.5.5`（默认 `graph=kuzu` + `vector=lancedb`），通过 MemoryMiddleware 集成

## 架构总览

```
三层Agent:  Orchestrator(L0) → Manager(L1) → Workers(L2)
通信:       Redis Streams (Consumer Group), 绝不用 Pub/Sub
调度:       自研 DAG Scheduler (Sorted Set 优先级 + Semaphore 并发控制)
记忆:       SessionMemory (单任务去重) + KnowledgeGraph (跨任务积累)
长文本FSM:  INIT → OUTLINE → OUTLINE_REVIEW → WRITING → PRE_REVIEW_INTEGRITY → REVIEWING → CONSISTENCY → [FINAL_INTEGRITY] → DONE
```

## 关键文件索引

| 路径 | 职责 |
|------|------|
| `backend/app/agents/base_agent.py` | Agent 基类 (Redis 消费循环 + 中间件管道) |
| `backend/app/services/dag_scheduler.py` | DAG 调度引擎 |
| `backend/app/services/long_text_fsm.py` | 长文本 FSM 控制器 |
| `backend/app/memory/session.py` | SessionMemory 统一 API |
| `backend/app/memory/knowledge/graph.py` | KnowledgeGraph 持久 API |
| `backend/app/utils/llm_client.py` | LLM 统一适配层 (OpenAI/DeepSeek + 降级) |
| `backend/app/utils/context_manager.py` | 三层记忆 + 渐进式披露 + 上下文压缩 |

## 关键约束（不可违反）

- **禁止** LangChain / LlamaIndex / Celery / socket.io / Redis Pub/Sub
- **禁止** 直接 `import openai`，必须通过 `llm_client.py`
- **禁止** 在业务代码中硬编码 prompt，必须用 `prompts/{role}/{action}.md`
- LLM 调用: 最多重试 3 次 + 自动降级到 fallback 模型
- Agent 中间件顺序: `Logging → TokenTracking → Timeout → ContextSummary → Memory → Agent`
- 记忆层: `MEMORY_ENABLED=false` 可一键关闭，退回 v1 行为
- pgvector 继续用于 RAG；记忆层向量检索走 cognee provider（默认 lancedb）
- 测试: MockLLMClient + fakeredis，测试不调外部 API

## 文档与编码（防乱码）

- 在 Windows PowerShell 做任何文本读写前，先执行：`.\scripts\enable_utf8_io.ps1`
- 文档修改优先 `apply_patch`，避免整文件重写式命令造成编码漂移
- 若发现乱码，先 `git restore` 目标文件，再按 UTF-8 流程重新补丁

## 文档索引

| 文档 | 位置 |
|------|------|
| 产品需求 | `docs/PRD.md` |
| 用户流程 | `docs/APP_FLOW.md` |
| 技术栈 | `docs/TECH_STACK.md` |
| 前端规范 | `docs/FRONTEND_GUIDELINES.md` |
| 后端架构 | `docs/BACKEND_STRUCTURE.md` |
| 实施计划 | `docs/IMPLEMENTATION_PLAN.md` |
| 经验教训 | `docs/lessons.md` |
| 进度追踪 | `docs/progress.md` |
| 任务路线 | `docs/task_plan.md` |
| 研究知识 | `docs/findings.md` |

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **thinkweave** (3043 symbols, 9257 relationships, 253 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/thinkweave/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/thinkweave/context` | Codebase overview, check index freshness |
| `gitnexus://repo/thinkweave/clusters` | All functional areas |
| `gitnexus://repo/thinkweave/processes` | All execution flows |
| `gitnexus://repo/thinkweave/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
