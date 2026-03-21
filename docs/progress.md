## 当前状态
已完成：Phase 0-2 + Step 3.1-3.3 + Step 4.1 + Step 4.1a
进行中：无
下一步：Step 4.1b — 记忆层基础设施（pip install cognee + 薄适配层）

## 文档更新（2026-03-18）
- 6 份规范文档 + CLAUDE.md + lessons.md 已融入 cognee Memory Layer 设计
- 来源：Aletheia v2 Architecture Design Spec + Memory Layer Design Spec（2026-03-17）
- 新增依赖：cognee 0.1.21 + Neo4j 5-community + Qdrant v1.12.0
- IMPLEMENTATION_PLAN.md：Phase 4 新增 Step 4.1b（记忆层基础设施）、Step 4.4（Knowledge Graph）
- PRD.md：新增 F5.5 记忆协调模块
- APP_FLOW.md：写作/审查/一致性阶段增加 Session Memory 交互
- TECH_STACK.md：新增 cognee/Neo4j/Qdrant 依赖，新增 Docker 服务表
- BACKEND_STRUCTURE.md：新增 memory/ 模块结构、MemoryMiddleware、四级去重设计
- CLAUDE.md：新增记忆层架构约束、6 条关键决策记录
- lessons.md：新增记忆层设计借鉴（8 条经验）

## Phase 2 Setup 完成记录（2026-03-06）
- Python 环境：uv + .venv (Python 3.13)，全部 16 个依赖已安装
- 前端环境：npm install 完成，所有依赖已安装
- Docker：PostgreSQL 15.8 (port 15432) + Redis 7.4 (port 6379) — 因本机已有 PG 服务，改用 15432
- Alembic 迁移：初始迁移 fe2c455b6ef4 — 7 张表 + 6 个索引全部创建成功
- 模型修正：Outline/ChapterReview 导出补齐、AgentHeartbeat 外键、task_id/node_id 索引
- Git：仓库初始化 + 推送到 github.com/nizigen/agentic-nexus (private)
- asyncpg 版本：0.29.0 → 0.31.0（0.29 在 Python 3.13 编译失败）

## 文档完善记录（2026-03-06）
- CLAUDE.md：重构，加入vibe-coding约束、会话启动协议、模型分配策略、工作流强制执行
- PRD.md：修复FSM（加入OUTLINE_REVIEW状态）、更新写作模式为并行、一致性Agent改为指出问题→写作Agent修改、审查阈值70分
- APP_FLOW.md：移除Agent通信时序图视图、更新一致性检查流程（问题清单→定向修改→再检查）
- TECH_STACK.md：Redis描述从Pub/Sub改为Streams Consumer Group、DeepSeek更新为V3.2、添加模型分配策略表
- BACKEND_STRUCTURE.md：修复Streams术语、Manager改为单一基类+role配置、FSM加入一致性循环+阈值常量、写作改为并行模式
- IMPLEMENTATION_PLAN.md：Step 3.1改为Redis Streams术语、Step 3.3加入agent_registry、Step 4.2/4.3更新为并行写作+一致性问题清单模式

## 第二轮审问更新（2026-03-06）
- PRD.md：添加生成模式定义（技术报告/小说/自定义）和研究深度（快速/标准/深入）
- APP_FLOW.md：移除参考资料上传，更新研究深度描述
- TECH_STACK.md：weasyprint→reportlab、加alembic、加@dnd-kit、加LLM降级策略、开发模式Docker只跑DB
- BACKEND_STRUCTURE.md：reference_files→target_words
- CLAUDE.md：添加关键决策记录表

## 已知问题
- pytest-asyncio deprecation warning: asyncio_default_fixture_loop_scope 未设置（不影响功能）
- DB集成测试需要Docker运行（PostgreSQL on port 15432, Redis on port 6379）

## 本次更新
2026-03-06：Step 0.2 后端基础框架验证通过（FastAPI + DB + Redis + 健康检查 200 OK）
2026-03-06：Step 0.3 前端基础框架完成（Ant Design暗色主题 / React Router 6路由 / 导航布局 / Axios / Zustand）
2026-03-07：Step 1.1 Agent CRUD API 完成 — 5个端点(GET list/POST/GET detail/PATCH status/DELETE) + 13个pytest测试全部通过
2026-03-07：Step 1.2 前端Agent管理页完成 — 列表表格+统计卡片+注册Modal+详情Drawer+搜索筛选+状态切换+删除确认
2026-03-07：Step 2.1 LLM适配层完成 — chat/chat_stream/chat_json/chat_with_tools/embed + 自动降级 + Token追踪 + Prompt模板 + Mock测试
2026-03-07：Step 2.1b 技能系统+MCP客户端完成 — Skills YAML解析/加载/匹配 + MCP配置/注册表/客户端(stub) + 代码审查修复（不可变性/路径安全/命令白名单）
2026-03-07：Step 2.1c 上下文管理+RAG检索完成 — 三层记忆/渐进式披露/上下文压缩 + 章节分块/嵌入/混合检索(RRF) + 代码审查修复（不可变配置/SHA256去重/zip strict）
2026-03-07：Step 2.2 任务分解服务完成 — validate_task_input + decompose_task + DAG验证 + 29测试用例
2026-03-09：Step 2.3 任务API完成 — POST /api/tasks（创建+分解+DAG持久化）+ GET /api/tasks/{id}（含节点树）+ GET /api/tasks（历史列表）+ TaskCreate pydantic校验（mode/depth/target_words）+ task_service服务层 + 16测试用例（6验证测试通过，10 DB集成测试需Docker）
2026-03-09：Step 3.1 Redis Streams通信中间件完成 — redis_streams.py（XADD/XREADGROUP/XACK/ConsumerGroup + SortedSet超时 + Hash状态）+ communicator.py（任务分配/结果上报/状态更新/系统日志/消息持久化）+ heartbeat.py（心跳发送/存活检测/过期扫描）+ timeout_monitor.py（后台轮询/回调/优雅停止）+ 43测试用例全部通过
2026-03-09：Step 3.2 DAG调度引擎核心完成 — dag_scheduler.py（DAGScheduler类：就绪节点检测/Agent角色匹配/Semaphore并发控制/任务分配+状态流转/超时检测/失败重试最多3次/死锁检测/Task完成标记）+ Scheduler Registry（start/stop/get）+ 25测试用例全部通过 + code-review修复2项（VALID_MODES排序/LLM client依赖注入）
2026-03-09：Step 3.3 Agent基类+层级Agent完成 — middleware.py（4层中间件：Logging/TokenTracking/Timeout/ContextSummary）+ base_agent.py（Redis Streams消费循环/心跳/中间件管道/结果上报）+ agent_registry.py（注册/注销/按role&layer查找/启停协程管理）+ orchestrator.py（Layer 0：调用task_decomposer生成DAG）+ manager.py（Layer 1：单基类+3角色strategy/coordinator/quality）+ worker.py（Layer 2：通用LLM子任务执行+Prompt模板自动加载）+ 38测试用例全部通过
2026-03-19：Step 4.1 长文本FSM完成 — long_text_fsm.py（LongTextState 8状态枚举/TRANSITIONS转换表/LongTextFSM类：transition+checkpoint+resume/InvalidTransitionError/scan_and_resume_running_tasks）+ Alembic迁移b3c4d5e6f7a8（checkpoint_data JSONB + error_message TEXT）+ 55测试用例全部通过 + 362全套回归测试0失败
2026-03-19：Step 4.1a cognee vendor spike完成 — 结论：不可行（依赖链>3000 LOC，35+核心依赖，无内置Qdrant适配器），降级为自研记忆层。cognify()实体提取=LLM结构化输出，可用chat_json()替代。产出spike报告（docs/spike_4_1a_cognee_vendor.md），更新TECH_STACK.md+IMPLEMENTATION_PLAN.md

2026-03-21: Step 4.1b kickoff (memory core) - added app/memory/{config,adapter,session,models}.py and backend/tests/test_memory_core.py; graceful degradation when MEMORY_ENABLED=false; targeted tests passed (6 new + 47 regression).

2026-03-21: Step 4.1b continued - added MemoryMiddleware in default pipeline order (Logging->Token->Timeout->ContextSummary->Memory), plus embedding/image registry tests and middleware tests; all targeted tests passed.

2026-03-21: Step 4.2 prep - WorkerAgent now forwards memory_context into writer template; write_chapter prompt added memory section; tests added and passed.
2026-03-21: Step 4.2 partial (specialized agents) - implemented OutlineAgent/WriterAgent/ReviewerAgent/ConsistencyAgent with role-enforced payload normalization; updated outline prompt with topic_claims requirement and reviewer prompt with overlap_findings injection; added tests in tests/test_specialized_agents.py; targeted tests passed.
2026-03-21: Agent config upgrade (high-star patterns) - added AgentConfig schema + agents.agent_config JSONB migration + API tests/validation for retries/tool-iterations/fallback-models/tool-allowlist; schema tests passed (3).
2026-03-21: Prompt upgrade from high-star patterns - added prompts/{outline,writer,reviewer,consistency}/system.md with role-goal-backstory + strict operating rules (inspired by CrewAI/AutoGen/open_deep_research patterns); validated with prompt/agent tests.
2026-03-21: Step 4.2 integration update - wired agent_config/model into runtime path (DAGScheduler assignment payload + Worker/Manager/Orchestrator LLM call params); added coverage in test_agent_core/test_dag_scheduler; targeted tests passed.

2026-03-21: Step 4.2 deep integration - connected agent_config.max_retries/fallback_models into runtime LLM retry/fallback path (resolve_llm_call_params -> Worker/Manager/Orchestrator calls -> task_decomposer.chat_json -> llm_client retry/fallback chain); added/updated tests in test_agent_core/test_llm_client/test_task_decomposer.

2026-03-21: Step 4.3 prompt/skill-injection kickoff - added stage-aware SkillLoader matching (role+mode+stage+priority), introduced StageSkillInjectionMiddleware in default middleware chain, wired Worker/Manager system prompt injection, upgraded reviewer/revise/consistency prompts with rubric+counterargument+closure-table+claim-check schemas, and expanded tests (test_skills/test_agent_core).

2026-03-21: Step 4.2 agent_config deep integration (closed loop)
- Added manager-path assertion to ensure `max_retries/fallback_models` are forwarded to `llm_client.chat(...)`.
- Synchronized six core vibe docs with explicit execution steps and acceptance criteria for Step 4.2.
- Related targeted tests executed and recorded in this session.
2026-03-21: Step 4.3D mid-entry detector integrated - added services/entry_stage.py to infer entry stage from draft_text/review_comments and enforce pre_review_integrity gate for mid-entry workflows; task creation now persists entry metadata in checkpoint_data and initializes fsm_state from detected entry stage; StageSkillInjectionMiddleware now auto-infers stage when explicit stage is absent.
- Added tests: tests/test_entry_stage.py (new), middleware inference tests in tests/test_agent_core.py, and task API coverage for draft/review-comment entry in tests/test_task_api.py.
- Verification: targeted non-DB tests passed (entry_stage + StageSkillInjectionMiddleware). Full task API tests currently blocked by local PostgreSQL connectivity in this environment.
2026-03-21: Step 4.3B/4.3E prompt-contract lane completed via strict TDD.
- Added `prompts/consistency/check_claims.md` (claim-level integrity-check prompt with verified/weak/unverifiable schema).
- Added `tests/test_prompt_contracts.py` to enforce reviewer/revise/consistency prompt contracts.
- Fixed runtime rendering bug: escaped JSON example braces in `prompts/reviewer/review_chapter.md` and `prompts/writer/revise_chapter.md` to avoid `PromptLoader.format_map` KeyError.
- Verification: `pytest backend/tests/test_prompt_contracts.py backend/tests/test_prompt_loader.py -q` => 16 passed.
2026-03-21: Step 4.3C observability follow-up via tri-plugin stages.
- Added skill-injection trace logging in `BaseAgent.process_task()`; when `_skill_injection_trace` exists, log binds `task_id/node_id/skill_injection_trace` for debugging.
- Added unit test `test_process_task_logs_skill_injection_trace` in `tests/test_agent_core.py`.
- Verification: `pytest backend/tests/test_agent_core.py -k "StageSkillInjectionMiddleware or default_middlewares_count or skill_injection_trace" -q` => 4 passed.
2026-03-21: Step 4.3A checkpoint policy implemented via tri-plugin TDD.
- Added `CheckpointPolicy` enum to `long_text_fsm.py` with FULL/SLIM/MANDATORY modes.
- `LongTextFSM` now accepts `checkpoint_policy`; `get_checkpoint_data()` emits policy-aware payloads:
  - FULL: includes completed_chapters + review_retry_count + consistency_retry_count
  - SLIM: minimal fsm_state/checkpoint metadata
  - MANDATORY: includes required chapter progress while excluding heavy retry counters
- Added policy tests in `tests/test_long_text_fsm.py`.
- Verification: `pytest backend/tests/test_long_text_fsm.py -k "CheckpointPolicy or TestConstants" -q` => 7 passed.
- Note: full `test_long_text_fsm.py` remains blocked by local PostgreSQL connectivity in this environment.
2026-03-21: Step 4.2 bugfix (tri-plugin Stage 2 execution) - fixed WriterAgent payload normalization to include `memory_context` (ctx-level preferred, payload fallback), preventing `write_chapter` template key-miss fallback and restoring memory-guided drafting behavior.
- Verification: `.\\backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_specialized_agents.py::test_writer_agent_injects_memory_context_into_prompt` => 1 passed; `.\\backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_specialized_agents.py` => 4 passed.
2026-03-22: Step 4.3D entry-stage bootstrap wiring completed via tri-plugin TDD.
- Added optional task input fields `draft_text` / `review_comments` in `TaskCreate` schema.
- Wired `task_service.create_task()` to call `build_entry_metadata(...)` and persist:
  - `tasks.fsm_state` from detected `entry_stage`
  - `tasks.checkpoint_data` with `entry_stage` + `entry_inputs` flags
- Added non-DB unit tests `backend/tests/test_task_service_entry_stage.py` with fake session + decomposer monkeypatch:
  - title-only keeps `fsm_state=init`
  - mid-entry draft routes to `fsm_state=pre_review_integrity`
- Verification:
  - `.\\backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_task_service_entry_stage.py backend/tests/test_entry_stage.py` => 6 passed.
2026-03-22: Step 4.3D API coverage + dual-review evidence lane.
- Added API tests for mid-entry routing in `backend/tests/test_task_api.py`:
  - `draft_text` request -> `fsm_state=pre_review_integrity`
  - `review_comments` request -> `fsm_state=pre_review_integrity`
- Security review finding fixed (MEDIUM): `TaskCreate` previously accepted unbounded `draft_text/review_comments`, risking oversized payload abuse.
  - Fix: added schema limits in `backend/app/schemas/task.py` (`draft_text<=200000`, `review_comments<=50000`)
  - Added schema tests in `backend/tests/test_task_schema_entry_inputs.py` (3 tests).
- Verification:
  - `.\\backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_task_schema_entry_inputs.py backend/tests/test_task_service_entry_stage.py backend/tests/test_entry_stage.py` => 9 passed.
  - `.\\backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_task_api.py -k \"draft_text_enters_pre_review_integrity or review_comments_enters_pre_review_integrity\"` blocked by local PostgreSQL connection reset in this environment.
