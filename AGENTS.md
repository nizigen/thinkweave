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
