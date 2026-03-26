## 文档同步（2026-03-22）
- 已吸收可复用设计：分层推进、生命周期 hook、SessionMemory 优先落地。
- 已明确本仓库 provider 真值：`cognee==0.5.5`，默认 `kuzu+lancedb`。

## 编码与记忆口径固化（2026-03-22）
- 已更新根规范：`CLAUDE.md`、`AGENTS.md`，写入当前记忆层真值与 PowerShell UTF-8 防乱码流程。
- 已新增根记忆文件：`MEMORY.md`（记录长期稳定口径，防后续会话漂移）。
- 已补充 `docs/lessons.md`：新增”Windows PowerShell 乱码教训”与恢复流程。

## 记忆层文档重构（2026-03-23）
- 移除 MemoryConfig 中废弃的 neo4j/qdrant 配置字段和测试
- 清理 adapter.py 中冗余的 neo4j/qdrant 显式拒绝逻辑（已由白名单覆盖）
- 统一 TECH_STACK.md / BACKEND_STRUCTURE.md / CLAUDE.md 中记忆层引用为 kuzu+lancedb
- 确认 cognee==0.5.5 是 PyPI 最新版，Windows 原生支持，无需 Docker

## Step 4.3 FSM 输出组装 + SessionMemory 生命周期（2026-03-23）
- 新增 `LongTextFSM.initialize_session_memory(session)`: 显式初始化 SessionMemory，将 namespace 持久化到 checkpoint_data（所有后续 transition 均保留）
- 新增 `LongTextFSM.finalize_output(session)`: 查询 writer 节点，natural sort 排序（修复 10+ 章节乱序 bug），拼接 output_text，更新 word_count
- `get_checkpoint_data()` base dict 加入 `session_memory_namespace`，确保每次 transition 不丢失 namespace
- `resume()` 恢复时读取 `session_memory_namespace` 到实例属性
- 修复 `test_prompt_contracts.py`: reviewer prompt 测试补充 `topic_claims` + `assigned_evidence` 缺失参数
- 三插件双审查：代码审查 3 HIGH 已修复；安全审查 0 CRITICAL/HIGH，2 MEDIUM 已知悉
- 114 非 DB 测试通过，commit: c81c014

## Step 4.4 Knowledge Graph（2026-03-23）
- 新增 `app/memory/knowledge/graph.py`：KnowledgeGraph（add_entry 按 key 去重取高置信度、tokenised query 前缀匹配、90 天 TTL prune_stale、to_context_string）
- 新增 `app/memory/knowledge/promotion.py`：promote_session()（筛选 credibility≥0.7，写入 KG）
- `session.cleanup()` 新增 `kg` + `topic` 参数；使用 topic 作为查询锚点，sha1 作为稳定 key fallback
- `MemoryMiddleware` 新增 `knowledge_graph` 参数；`before_task` 为 outline/writer 角色注入 `kg_context`
- 代码审查 2 HIGH 修复完成，15 新测试，129 非 DB 测试全绿，commit: 8e1f3c6

## 基线集成测试（2026-03-23，Docker 在线）
- 完整测试套件：**437 passed，4 pre-existing failures**
  - `test_mcp.py` 2 个：MCP 配置断言预存 bug
  - `test_task_service_entry_stage.py` 2 个：`_FakeSession` 缺少 `commit` 方法，预存 bug
- 修复：conftest.py 自动加载 `.env`（dotenv），无需手动传 POSTGRES_URL
- PostgreSQL: localhost:15432，Redis: localhost:6379，均正常
- commit: a58a704

## Step 6.1 导出服务后端（2026-03-26）
- 新增 `app/services/exporter.py`：BaseExporter 抽象基类 + DocxExporter（python-docx） + PdfExporter（reportlab + STSong-Light CID 字体中文支持）+ parse_markdown_blocks（标题/代码块/段落解析）
- 新增 `app/routers/export.py`：GET /api/export/{task_id}/docx|pdf，StreamingResponse，RFC 5987 中文文件名编码，404/409 错误处理
- 新增 `tests/test_exporter.py`：16 测试全绿，三插件双审查通过（无 CRITICAL/HIGH）
- commit: 6bffd04

## 当前状态
已完成：Phase 0-2 + Step 3.1-3.3 + Step 4.1 + Step 4.1a + Step 4.1b + Step 4.2 + Step 4.3 + Step 4.4 + Step 5.1 + Step 5.2 + Step 5.3 + Step 5.4 + Step 5.5/5.6 控制塔首版 + 基线集成测试 + Step 6.1
进行中：Phase 6
下一步：Step 6.2 前端结果展示页

## Step 5.5 / 5.6 控制塔首版（2026-03-25）
- 后端新增任务控制链路：`pause/resume/skip/retry` REST API、`task_control.py` 服务、调度器协作暂停/恢复/跳过/重试语义、事件桥接兼容 `node_update/dag_update/log/chapter_preview/review_score/consistency_result`
- `GET /api/tasks/{id}` 详情扩展为监控恢复快照：节点 `started_at/finished_at/assigned_agent`、`checkpoint_data.control`、`preview_cache`、`review_scores`
- 前端 `monitorStore` 升级为归一化监控状态：节点映射、控制状态、章节预览、评分、一致性结果、节点选择、事件归并
- 监控页升级为 Control Tower 首版：`DagViewer`、`ControlToolbar`、`AgentPanel`、`LogStream`、`FsmProgress`、`ChapterPreview`，支持控制命令与回连重同步
- 根据 Stage 3 code review 修复两处状态同步缺陷：
  - 控制命令异步响应不再覆盖已切换任务
  - 快照重建时清空易陈旧的 agent/consistency 派生缓存
- 验证：
  - backend: `tests/test_task_control.py tests/test_dag_scheduler.py tests/test_event_bridge.py tests/test_task_api.py tests/test_redis_streams.py` => `156 passed`
  - frontend: `monitorStore + useTaskWebSocket + Monitor/DagViewer/ControlToolbar` => `20 passed`
- Stage 3 结果：
  - code review subagent: `APPROVED`
  - security review subagent: 无 `CRITICAL/HIGH`；保留 2 个 `MEDIUM` 残留风险，均与现有 token 传递模型有关（`sessionStorage` Bearer token、WebSocket subprotocol 携带可逆 token）

## Step 5.4 前端 WebSocket 连接层（2026-03-24）
- 新增 `frontend/src/stores/monitorStore.ts`：维护监控页独立连接状态、任务快照、最近 500 条事件缓存，隔离于 `taskStore`
- 新增 `frontend/src/hooks/useTaskWebSocket.ts`：接入浏览器可用的 `Sec-WebSocket-Protocol` 鉴权握手，支持指数退避重连与重连后的 REST 全量同步
- 更新 `backend/app/routers/ws.py`：支持 base64url 编码 token 的 subprotocol 鉴权，并在握手时显式接受 `agentic-nexus.auth`
- 更新 `frontend/src/pages/Monitor.tsx`：显示连接状态、重连次数和错误提示，作为 Step 5.5/5.6 可视化前的轻量监控入口
- 新增前端测试栈：`vitest@4.1.1`、`@testing-library/react@16.3.2`、`@testing-library/jest-dom@6.9.1`、`jsdom@29.0.1`
- 根据双审查补强竞态保护：阻止旧任务快照覆盖、忽略跨任务/过期 socket 事件、对 `1008` 终止性关闭码停止重连并保留明确错误
- 验证通过：`backend/tests/test_ws_endpoint.py backend/tests/test_ws_manager.py backend/tests/test_event_bridge.py` => `41 passed`；`frontend npm run test` => `11 passed`；Step 5.4 相关前端 eslint 通过

## 文档更新（2026-03-18）
- 6 份规范文档 + CLAUDE.md + lessons.md 已融入 cognee Memory Layer 设计
- 来源：Aletheia v2 Architecture Design Spec + Memory Layer Design Spec（2026-03-17）
- 新增依赖方向：`cognee==0.5.5`（memory）+ `pgvector`（RAG），memory 默认 provider 为 `kuzu+lancedb`
- IMPLEMENTATION_PLAN.md：Phase 4 新增 Step 4.1b（记忆层基础设施）、Step 4.4（Knowledge Graph）
- PRD.md：新增 F5.5 记忆协调模块
- APP_FLOW.md：写作/审查/一致性阶段增加 Session Memory 交互
- TECH_STACK.md：新增 cognee 依赖（kuzu+lancedb 默认 provider），新增 Docker 服务表
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

2026-03-22: Step 4.3 dedup metric landed - added `backend/app/services/dedup_quality.py` with `evaluate_dedup_quality(session, task_id)` and pairwise cosine duplicate-rate report (`threshold=0.85`).
- Added tests: `backend/tests/test_dedup_quality.py` (3 passed).
- Regression spot-check: `.\\backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_memory_core.py::TestSessionMemory::test_session_lifecycle` (1 passed).

2026-03-22: tri-plugin Stage 1-3 execution (dedup API subflow)
- Stage 1 (planning): 目标收敛为 Step 4.3 对外触发闭环（API 暴露 + DoS 上限 + 测试补盲）。
- Stage 2 (TDD): 新增 `GET /api/tasks/{task_id}/dedup-quality`，新增响应 schema，补充 API/服务测试，定向测试 `6 passed`。
- Stage 3 (dual review via subagents): 代码审查通过；安全审查剩余 1 个 HIGH（全局鉴权/授权缺失，影响 `GET /api/tasks/{task_id}` 与 dedup 接口）。
- 状态：**BLOCKED BY PROCESS**（需产品/架构决策：是否在本轮引入任务级鉴权）。

2026-03-22: tri-plugin follow-up closure (authz hardening)
- Stage 2 fix: 所有任务读接口统一改为 `Authorization: Bearer <token>` 认证，服务端由 `settings.task_auth_tokens` 映射 token→user，再进行任务 owner 授权校验。
- Stage 2 fix: `create/list/get/dedup` 全链路按同一 user_id 口径执行，关闭“匿名创建后不可读”和“列表可枚举”漏洞。
- Stage 2 fix: `task_service.list_tasks` 增加 owner 过滤；dedup 度量保留 `max_chapters/max_chars_per_chapter` 上限与稳定排序。
- Tests: `backend/tests/test_task_api.py::{TestGetTask,TestTaskDedupQuality,TestListTasks}` + `backend/tests/test_dedup_quality.py` => `15 passed`。
- Stage 3 (dual review via subagents): code review **No findings**；security review **No findings**。
- 状态：**UNBLOCKED**（本轮三阶段闭环完成，可继续下一实现项）。

2026-03-22: tri-plugin Stage 1-3 (Step 4.3 baseline compare subflow)
- Stage 1: 收敛为“基线对比 API 子流程”交付（baseline vs candidate，目标阈值可配置，沿用任务级授权）。
- Stage 2: 新增 `GET /api/tasks/dedup-compare`，输出 `baseline_report/candidate_report/duplicate_rate_delta/goal_threshold/goal_met`；并补 `TaskDedupCompareRead` schema 与 compare service。
- Stage 2 security hardening: 授权来源从 `checkpoint_data` 迁移到 `tasks.owner_id`（新增迁移 `d5e6f7a8b9c0_add_owner_id_to_tasks.py`），对象级未授权统一返回 `404`，`goal_threshold` 限制为 `[0,1]`。
- Tests: `backend/tests/test_task_api.py::{TestGetTask,TestTaskDedupQuality,TestTaskDedupCompare,TestListTasks}` + `backend/tests/test_dedup_quality.py` => `22 passed`。
- Stage 3: code review subagent **No findings**；security review subagent **No findings**。

2026-03-22: Step 4.3 dedup compare subflow completed via tri-plugin TDD.
- Added `GET /api/tasks/dedup-compare?baseline_task_id=...&candidate_task_id=...` with Bearer auth + owner checks.
- Added compare response schema and service helper returning `baseline_report`, `candidate_report`, `duplicate_rate_delta`, `goal_threshold`, `goal_met`.
- Added tests for success, `401`, `403`, `404`; compare-related suite now passes (`16 passed` for targeted task API + dedup tests).
- Verification: `.\\backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_task_api.py::TestTaskDedupCompare backend/tests/test_dedup_quality.py::test_compare_dedup_quality_builds_delta_report` => 5 passed; `.\\backend\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_task_api.py::TestGetTask backend/tests/test_task_api.py::TestTaskDedupQuality backend/tests/test_task_api.py::TestListTasks backend/tests/test_dedup_quality.py` => 16 passed.
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

2026-03-23: Step 4.2 agent contract upgrade completed via vibe tri-plugin flow.
- Kept the current runtime architecture (OutlineAgent, WriterAgent, ReviewerAgent, ConsistencyAgent) and upgraded their payload contracts based on the academic-paper reference agents.
- Added role-aware MemoryMiddleware as the default final middleware in the required order: Logging -> TokenTracking -> Timeout -> ContextSummary -> Memory.
- Rewrote the specialized prompts to require explicit handoff fields (topic_claims, assigned_evidence, chapter summaries, consistency issue families).
- Verification:
  - backend/.venv/Scripts/python.exe -m pytest -q tests/test_memory_middleware.py tests/test_agent_core.py tests/test_specialized_agents.py tests/test_agent_prompt_contracts.py -> 53 passed.
  - backend/.venv/Scripts/python.exe -m pytest -q tests/test_review_fixes.py tests/test_llm_client.py tests/test_agents.py tests/test_long_text_fsm.py::TestCheckpoint tests/test_memory_core.py tests/test_task_api.py -> 85 passed.
- Follow-up hardening: MemoryMiddleware now degrades gracefully on query/store failures and caps in-process cached sessions to avoid unbounded growth in long-lived workers.
## Step 5.1-5.2 WebSocket 实时桥接（2026-03-24）
- 验收并收口现有 `app/routers/ws.py` 与 `app/services/ws_manager.py`：WebSocket 握手、鉴权、心跳、路由注册继续保持可用
- 新增 `app/schemas/ws_event.py`：统一 WebSocket 事件结构，覆盖 `connected` / `node_update` / `log` / `task_done` / `chapter_preview` / `review_score` / `consistency_result` / `dag_update`
- 新增 `app/services/event_bridge.py`：为每个 `task_id` 维护单例 Redis→WebSocket 桥接协程，兼容现有 `status_update -> node_update` 映射
- `app/routers/ws.py` 接入桥接生命周期：连接成功后 `ensure_started(task_id)`，最后一个连接断开后 `stop(task_id)`
- 新增测试 `backend/tests/test_event_bridge.py`，并扩展 `backend/tests/test_ws_endpoint.py`
- 验证：
  - `backend/tests/test_event_bridge.py + test_ws_endpoint.py + test_ws_manager.py` => `26 passed`
  - `backend/tests/test_communicator.py + test_redis_streams.py` => `43 passed`
## Step 5.3 Agent / FSM 事件发射（2026-03-24）
- `communicator.py` 新增 `send_task_event()`，统一任务事件发送入口；`send_status_update()` 改为兼容封装
- `LoggingMiddleware` 现在会在开始/完成/失败时发 `node_update`
- `BaseAgent` 成功处理后会按角色补发：
  - writer -> `chapter_preview`
  - reviewer -> `review_score`
  - consistency -> `consistency_result`
- `DAGScheduler` 在任务完成/失败时补发 `task_done`
- `LongTextFSM.transition()` 默认发 `dag_update`，发送失败不阻塞状态迁移
- 验证：
  - `backend/tests/test_communicator.py + test_agent_core.py + test_dag_scheduler.py` => `89 passed`
  - `backend/tests/test_event_bridge.py + test_ws_endpoint.py + test_ws_manager.py` => `26 passed`
  - 事件发射目标集 `-k "send_task_event or emits or task_done or dag_update"` => `8 passed`

2026-03-24: Step 5 review-hardening follow-up completed.
- 修复 WebSocket 授权边界：无 `owner_id` 任务默认拒绝非管理员访问；默认仅接受 `Authorization: Bearer`，query token 回退改为显式配置开关。
- 修复 WebSocket 来源校验：移除硬编码 localhost，统一改为读取 `settings.cors_allow_origins`，与 HTTP CORS 配置保持一致。
- 修复握手/时序问题：`connected` 事件改为先于 `event_bridge.ensure_started()` 发送，避免任务事件抢在握手帧之前抵达。
- 修复 bridge 启动窗口漏事件：连接建立后先读取当前 stream 游标，再以该游标启动 bridge，避免握手后的首批事件被 `$` 跳过。
- 修复已有 bridge 下的新订阅时序：连接先进入 pending，待 `connected` 发出后再激活到广播集合，避免第二个及后续订阅者先收到业务事件。
- 修复大消息处理：超出 `MAX_WS_MESSAGE_SIZE` 的客户端消息现在直接关闭连接，不再静默忽略。
- 修复事件桥稳定性：`TaskEventBridge` 增加并发锁，避免重复启动；读取/广播瞬时失败时按退避重试，不再直接退出。
- 修复事件暴露：`LoggingMiddleware` 失败事件改为发送安全摘要（`error_code`/`error_message`），不再广播原始异常字符串。
- 新增回归测试覆盖：ownerless task 拒绝、配置化 origin、Bearer header、握手顺序、超大消息关闭、bridge 并发安全、bridge 瞬时失败恢复、错误载荷脱敏。
- 定向验证：
  - `backend/tests/test_agent_core.py + test_event_bridge.py + test_ws_endpoint.py` => `66 passed`
  - `backend/tests/test_communicator.py + test_agent_core.py + test_dag_scheduler.py + test_event_bridge.py + test_ws_endpoint.py + test_ws_manager.py` => `129 passed`
  - `backend/tests/test_long_text_fsm.py` 在本机因 PostgreSQL 连接拒绝未纳入本轮通过集，需在测试库可用后补跑。
