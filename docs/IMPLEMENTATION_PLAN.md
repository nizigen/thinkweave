# IMPLEMENTATION_PLAN.md — 实施计划

## 原则
- 每步只做这一步，不跳跃
- 每步完成后更新 progress.md
- 每步完成前必须能跑通（可以功能残缺，但不能报错崩溃）

---

## Phase 0：项目脚手架（第3-4周）

### Step 0.1 — 项目目录初始化
- [x] 创建 `backend/` 和 `frontend/` 目录结构
- [x] 初始化 Python 虚拟环境（conda），安装依赖
- [x] 初始化 React + Vite + TypeScript 项目
- [x] 配置 `docker-compose.yml`（PostgreSQL + Redis）
- [x] 创建 `.env` 和 `.env.example`

### Step 0.2 — 后端基础框架
- [x] 搭建 FastAPI 应用入口（main.py）
- [x] 配置数据库连接（asyncpg + SQLAlchemy）
- [x] 配置 Redis 连接
- [x] 运行数据库迁移（建表）
- [x] 搭建 loguru 日志
- [x] 健康检查接口：`GET /health` 返回200

### Step 0.3 — 前端基础框架
- [x] 配置 Ant Design（暗色主题，覆盖token）
- [x] 配置 React Router（5个页面路由）
- [x] 搭建左侧导航栏 + 顶部导航栏布局
- [x] 配置 Axios 请求拦截器
- [x] 配置 Zustand store 基础结构

**验收：** `docker compose up` 启动，前端能访问，后端健康检查通过

---

## Phase 1：Agent管理模块（第5周前半）

### Step 1.1 — 后端Agent CRUD
- [x] 实现 Agent ORM模型 + Pydantic Schema
- [x] 实现 `GET /api/agents` — 列表
- [x] 实现 `POST /api/agents` — 注册
- [x] 实现 `GET /api/agents/{id}` — 详情
- [x] 实现 `PATCH /api/agents/{id}/status` — 状态更新
- [x] 实现 `DELETE /api/agents/{id}` — 删除
- [x] 用 pytest 写基础CRUD测试

### Step 1.2 — 前端Agent管理页
- [x] Agent列表表格（含状态徽章）
- [x] 注册新Agent的表单Modal
- [x] Agent详情抽屉（历史任务、执行率）
- [x] 停用/删除操作确认

**验收：** 可以在UI上注册Agent、查看列表、更新状态

---

## Phase 2：任务分解引擎（第5-6周）

### Step 2.1 — LLM适配层
- [x] 实现 `llm_client.py` 模型配置注册表（ModelConfig dataclass + ROLE_MODEL_MAP）
- [x] 实现统一 `chat()` 接口（按role自动选模型，OpenAI/DeepSeek双provider）
- [x] 支持流式输出 `chat_stream()`（AsyncIterator[str]）
- [x] 支持结构化JSON输出 `chat_json()`（response_format + schema校验）
- [x] 支持工具调用循环 `chat_with_tools()`（function calling + MCP工具执行）
- [x] 错误重试（最多3次，指数退避 1s→2s→4s）
- [x] 模型自动降级（主模型失败→fallback模型，双向互备）
- [x] Token用量追踪（`token_tracker.py`，按task_id/agent_role聚合）
- [x] 实现文本嵌入接口 `embed()`（通过OpenAI SDK调用text-embedding-3-small）
- [x] 实现Prompt前缀优化（静态在前/变量在后，最大化provider缓存命中）
- [x] 记录缓存命中指标（OpenAI cached_tokens / DeepSeek cache_hit_tokens）
- [x] 实现 `prompt_loader.py`（从 prompts/ 目录加载Markdown模板，str.format_map 渲染变量）
- [x] 创建初始Prompt模板文件（orchestrator/decompose.md、outline/generate.md、writer/write_chapter.md、reviewer/review_chapter.md、consistency/check.md）
- [x] 实现 `BaseLLMClient` 抽象基类（ABC，定义 chat/chat_json/embed 接口）
- [x] 实现 `MockLLMClient`（测试用，按角色返回预设响应，记录调用日志）
- [x] 创建 `tests/conftest.py` 基础fixture（mock_llm、db_session、mock_redis）

### Step 2.1b — 技能系统 + MCP客户端
- [x] 实现技能数据模型（`skills/types.py`：Skill dataclass，含frontmatter字段）
- [x] 实现Markdown+YAML frontmatter解析（`skills/parser.py`）
- [x] 实现技能加载器（`skills/loader.py`：扫描skills/目录，按role+mode匹配）
- [x] 创建初始技能文件（writing_styles/technical_report.md、novel.md）
- [x] 实现MCP客户端管理器（`mcp/client.py`：连接/断开/工具调用）
- [x] 实现MCP工具注册表（`mcp/registry.py`：汇总工具列表，转OpenAI tools格式）
- [x] 实现MCP配置加载（`mcp/config.py`：从mcp_servers.json读取）
- [x] 创建 `mcp_servers.example.json` 配置示例

### Step 2.1c — 上下文管理 + RAG检索
- [x] 实现 `context_manager.py` 三层记忆架构（Working/Task/Persistent）
- [x] 实现渐进式披露（按Agent角色组装不同粒度的上下文）
- [x] 实现上下文压缩（超过模型窗口75%时用DeepSeek摘要旧上下文）
- [x] 实现章节摘要生成（写完后自动摘要存入Task Memory）
- [x] Docker镜像切换（postgres:15.8 → ankane/pgvector:pg15）
- [x] 创建 `document_chunks` 表迁移（pgvector + tsvector）
- [x] 实现 `rag/chunker.py`（章节级 + 段落级分块）
- [x] 实现 `rag/embedder.py`（通过LLMClient.embed()批量嵌入）
- [x] 实现 `rag/retriever.py`（混合检索：pgvector语义 + PG全文搜索 + RRF融合）
- [x] 实现 `RetrievalMiddleware`（rag_enabled=false时零开销）

### Step 2.2 — 任务分解服务
- [x] 实现输入验证 `validate_task_input()`（标题长度、mode合法性检查）
- [x] 实现 `task_decomposer.py`
- [x] 设计分解Prompt（few-shot示例，覆盖技术报告/小说两种模式）
- [x] 解析LLM返回的DAG JSON（通过 `chat_json()` + schema校验）
- [x] 验证DAG合法性（无环检测）
- [x] 将分解结果写入数据库（将在Step 2.3 任务API中一起实现）

### Step 2.3 — 任务API
- [x] 实现 `POST /api/tasks`（创建任务 + 触发分解）
- [x] 实现 `GET /api/tasks/{id}`（含DAG节点树）
- [x] 实现 `GET /api/tasks`（历史列表）

**验收：** POST创建任务后，数据库中出现正确的DAG节点数据

---

## Phase 3：DAG调度引擎（第6-7周）

### Step 3.1 — Redis Streams通信中间件
- [x] 实现 `redis_streams.py`（XADD/XREADGROUP/XACK封装）
- [x] 实现 `communicator.py`（业务层消息收发）
- [x] Agent任务分配：XADD到 `agent:{agent_id}:inbox` Stream（Consumer Group模式）
- [x] Agent结果上报：XADD到 `task:{task_id}:events` Stream
- [x] Redis Sorted Set实现超时监控（`scheduler:timeout_watch`）
- [x] Redis Hash实现Agent状态存储（`agent:{agent_id}:state`）
- [x] 消息持久化到 messages 表

### Step 3.2 — 调度引擎核心
- [x] 实现 `dag_scheduler.py`
- [x] 就绪节点检测（前置依赖全部完成）
- [x] Agent匹配（按角色 + 空闲状态）
- [x] 并发控制（MAX_CONCURRENT_LLM_CALLS / MAX_CONCURRENT_WRITERS，超出排队）
- [x] 任务分配 + 状态流转
- [x] 失败重试（最多3次）+ 任务转移

### Step 3.3 — Agent基类 + 层级Agent
- [x] 实现 `base_agent.py`（Redis Streams消费、心跳上报、任务处理、结果返回）
- [x] 实现结构化日志（`logger.py`：loguru配置 + `logger.bind(task_id, agent_id, role)` 规范）
- [x] 实现 Agent 中间件管道（`middleware.py`：Logging / TokenTracking / Timeout / ContextSummary）
- [x] 实现 Orchestrator Agent（Layer 0：调用分解服务生成DAG）
- [x] 实现 Manager Agent（Layer 1：单一基类，通过role配置区分职责，协调执行层）
- [x] 实现简单 Worker Agent（Layer 2：调用LLM完成子任务）
- [x] 实现 `agent_registry.py`（Agent能力索引，用于调度器匹配）

**验收：** 创建任务后，调度器自动驱动Agent执行完所有节点

---

## Phase 4：长文本控制模块 + 记忆层（第7-9周）

### Step 4.1 — 长文本FSM
- [x] 实现 `long_text_fsm.py`
- [x] 定义5个状态 + 转换规则
- [x] FSM状态持久化到 tasks.fsm_state
- [x] 实现检查点机制（`checkpoint()` 保存已完成章节/重试计数到 tasks.checkpoint_data JSONB）
- [x] 实现崩溃恢复（`resume()` 从checkpoint恢复FSM，跳过已完成章节，恢复重试计数）
- [x] 服务重启时扫描 status='running' 的任务，自动调用 resume()

### Step 4.1a — cognee vendor 验证 spike（2-4 小时）
- [x] 调研 cognee v0.1.21 + v0.5.5 仓库结构、依赖链、核心 API 实现
- [x] 画出 3 个 API 的 import 依赖链 → **结论：依赖链过深（>3000 LOC，35+ 核心依赖）**
- [x] 评估 `cognify()` 实体提取 → **可用 `llm_client.chat_json()` 完全替代**（cognee 内部也是 LLM 结构化输出）
- [x] 发现 cognee **无内置 Qdrant 适配器**（仅 LanceDB/PGVector/ChromaDB），Qdrant 必须自研
- [x] **触发降级方案**：不 vendor cognee，自研记忆层，参考 cognee 架构模式
- [x] 产出 spike 报告（`docs/spike_4_1a_cognee_vendor.md`），更新 TECH_STACK.md + Step 4.1b

### Step 4.1b — 记忆层基础设施（自研，参考 cognee 架构模式）
- [ ] Docker Compose 添加 Neo4j（5-community, port 7687/7474）+ Qdrant（v1.12.0, port 6333）
- [ ] 实现 `memory/config.py`（MemoryConfig，pydantic-settings，从 .env 加载 Neo4j/Qdrant/Embedding 配置，MEMORY_ENABLED 开关）
- [ ] 实现 `memory/models.py`（TopicClaim / ContentSummary / EntityRelation / KnowledgeGraph 数据模型，参考 cognee DataPoint 模式）
- [ ] 实现 `memory/embedding.py`（复用 llm_client.embed()，带 SHA256 内容哈希缓存）
- [ ] 实现 `memory/graph_store.py`（GraphStoreABC + Neo4jGraphStore + InMemoryGraphStore，参考 cognee GraphDBInterface 精简为 ~8 核心方法）
- [ ] 实现 `memory/vector_store.py`（VectorStoreABC + QdrantVectorStore + InMemoryVectorStore，参考 cognee VectorDBInterface 精简为 ~6 核心方法）
- [ ] 实现 `memory/entity_extractor.py`（LLM 结构化输出提取实体关系，通过 llm_client.chat_json() + KnowledgeGraph schema）
- [ ] 实现 `memory/image_registry.py`（图片 URL→章节映射，asyncio.Lock 防跨章节重复）
- [ ] 实现 `memory/session.py`（SessionMemory 统一 API：initialize/store/query/cleanup，namespace 隔离）
- [ ] 单元测试（InMemory 后端，mock Neo4j/Qdrant/Embedding）

### Step 4.2 — 专用Agent实现（含记忆集成）
- [ ] 实现 `outline_agent.py`（生成Markdown大纲，包含 context bridges + **topic_claims**：每章 owns + boundary）
- [ ] 实现 `writer_agent.py`（基于完整大纲+章节描述并行写作，**启动前从 Session Memory 读取其他章节摘要**）
- [ ] 实现 `reviewer_agent.py`（对每章评分0-100，≥70通过，**审查时检测内容重叠**）
- [ ] 实现 `consistency_agent.py`（全文扫描，**从 Session Memory 读取章节摘要而非全文**，降低 token 消耗）
- [ ] 实现 `MemoryMiddleware`（记忆层中间件：before_task 注入去重指令，after_task 写入摘要）
- [ ] 更新 Outline prompt 模板（`prompts/outline/generate.md`）：要求输出 topic_claims 字段
- [ ] 更新 Writer prompt 模板（`prompts/writer/write_chapter.md`）：增加 `{memory_context}` 占位符
- [ ] 更新 Reviewer prompt 模板：增加重叠检测结果注入

### Step 4.3 — 长文本生成流程集成（含记忆生命周期）
- [ ] FSM 进入 OUTLINE 状态时：**初始化 SessionMemory**（创建 session 命名空间）
- [ ] FSM 进入 OUTLINE 后：大纲生成后，**topic_claims 写入 SessionMemory.store_territory_map()**
- [ ] 大纲生成后进入OUTLINE_REVIEW，等待用户确认/编辑
- [ ] 写作Agent并行执行，每个Writer拿到完整大纲+自己的章节+**Session Memory 去重上下文**
- [ ] 审查不通过（<70分）或检测到重叠 → 回到WRITING状态对应章节重写（最多3次）
- [ ] 一致性不通过 → 问题清单发给对应Writer修改（最多2次循环）
- [ ] FSM 进入 DONE 时：**SessionMemory.cleanup()（可选提升数据到 Knowledge Graph）**
- [ ] 各章节文本拼接为完整文档
- [ ] 更新 tasks.output_text + tasks.word_count
- [ ] 检查点数据中包含 session_memory_id，崩溃恢复时可重新挂载
- [ ] 实现 `evaluate_dedup_quality(task_id)` 度量脚本：计算所有章节对的向量相似度，>0.85 判定为重复，输出重复率报告
- [ ] 基线测试：关闭记忆层生成一篇报告 → 跑度量脚本得基线；启用记忆层再生成 → 对比（目标 < 5%）

### Step 4.4 — Knowledge Graph（跨任务知识积累）
- [ ] 实现 `memory/knowledge/graph.py`（KnowledgeGraph：持久化查询/存储 API）
- [ ] 实现 `memory/knowledge/promotion.py`（Session→KG 数据提升：已验证引用、实体关系、术语定义）
- [ ] 任务完成时 SessionMemory.cleanup() 自动触发 promote（credibility ≥ 0.7 的数据提升到 KG）
- [ ] Outline/Writer Agent 启动前查询 KG 历史知识（通过 MemoryMiddleware.before_task）
- [ ] KG 条目 90 天 TTL（stale 后需重新验证）
- [ ] 集成测试（跨任务知识复用场景）

**验收：** 输入"写一篇量子计算技术报告"，系统输出≥8000字的结构化文档；并行章节内容重复率 < 5%（对比无记忆层的 20-30%）；第二次生成同主题报告时，能复用首次验证的引用和实体关系

---

## Phase 5：实时监控 + WebSocket（第10周）

### Step 5.1 — WebSocket后端
- [ ] 实现 `/ws/task/{task_id}` 端点
- [ ] 监听Redis各channel，转发给WebSocket客户端
- [ ] 消息类型：node_update / log / agent_status / task_done

### Step 5.2 — 前端监控页（重点页面）
- [ ] 集成 @antv/g6，渲染DAG图
- [ ] WebSocket连接 + 实时更新节点颜色/状态
- [ ] 执行中节点：边框发光动画
- [ ] Agent活动面板（右上）
- [ ] 执行日志流（右下，自动滚动）
- [ ] FSM进度条（顶部）

**验收：** 运行任务时，前端DAG实时变色，日志实时滚动

---

## Phase 6：结果展示 + 导出（第10-11周）

### Step 6.1 — 导出功能
- [ ] 实现 DOCX 导出（python-docx）
- [ ] 实现 PDF 导出（weasyprint）
- [ ] 实现导出API（流式文件响应）

### Step 6.2 — 前端结果页
- [ ] Markdown渲染（react-markdown + 代码高亮）
- [ ] 文档目录（章节锚点）
- [ ] 导出按钮（DOCX/PDF）
- [ ] 生成统计展示

### Step 6.3 — 历史任务页
- [ ] 任务列表表格
- [ ] 搜索/筛选
- [ ] 点击查看历史结果

**验收：** 完整走通一次任务：创建 → 监控 → 查看结果 → 导出DOCX

---

## Phase 7：系统集成测试（第11周）

- [ ] 端到端测试：技术报告生成完整流程
- [ ] 端到端测试：小说写作完整流程
- [ ] Agent失败恢复测试
- [ ] WebSocket断线重连测试
- [ ] 导出文件格式验证

---

## progress.md 更新规范

每完成一个Step后立即更新：

```
## 当前状态
已完成：Step 0.1, 0.2, 0.3, 1.1
进行中：Step 1.2（前端Agent管理页）
下一步：Step 2.1（LLM适配层）

## 已知问题
- WebSocket在Windows上有时连接超时（待查）

## 本次更新
2026-03-05：完成Step 0.x，项目骨架搭建完毕
```

---

## 2026-03-21 Addendum (Step 4.2 Integration)

To align new agent profile configuration with runtime behavior, add these mandatory items:

- [x] Scheduler dispatch payload includes `model` and `agent_config` from `agents` table.
- [x] Worker/Manager/Orchestrator consume runtime LLM overrides from payload:
  - `model`
  - `agent_config.max_tokens`
  - `agent_config.temperature`
- [x] Unit tests for runtime integration:
  - worker call parameter propagation
  - scheduler payload propagation
- [x] Extend retry/fallback behavior to consume `agent_config.max_retries` and `agent_config.fallback_models` in `llm_client` orchestration path.

Notes:
- This keeps API-level configuration and execution behavior consistent.
- Existing role-based model routing remains default when overrides are absent.

---

## 2026-03-21 Addendum (Academic Research Skills Mapping)

### Step 4.3A -> Flow Gate Integration
- [ ] Extend `long_text_fsm.py` states with:
  - `pre_review_integrity`
  - `re_review`
  - `re_revise`
  - `final_integrity`
- [ ] Implement transition guards for integrity/review mandatory gates.
- [ ] Add checkpoint policy enum: `FULL | SLIM | MANDATORY`.

### Step 4.3B -> Prompt Hardening (Writing-Oriented)
- [ ] Update reviewer prompt to output rubric JSON (0-100 + must_fix + strongest_counterargument).
- [ ] Update revision prompt to output closure table (`issue -> action -> evidence`).
- [ ] Add integrity-check prompt for claim-level verification (`verified/weak/unverifiable`).

### Step 4.3C -> Skill Injection Refinement
- [ ] Add stage-aware skill profile resolution in skill loader.
- [ ] Inject stage skill snippets before model call with deterministic order.
- [ ] Persist resolved injection trace for observability/debugging.

### Step 4.3D -> Mid-Entry Support
- [ ] Add entry-stage detector from user materials (title/draft/review comments).
- [ ] Enforce non-skippable integrity stage even for mid-entry workflows.

### Step 4.3E -> Tests
- [ ] FSM transition tests for new states and guardrails.
- [ ] Prompt output schema tests (rubric / closure / integrity JSON).
- [ ] Middleware injection-order tests.
- [ ] End-to-end tests: write -> pre_integrity -> review -> revise -> final_integrity -> done.
- [ ] Mid-entry e2e tests: draft-entry / review-comment-entry.

---

## 2026-03-21 Step 4.2 Agent Config Deep Integration (Execution Steps)

Scope: wire `agent_config.max_retries` and `agent_config.fallback_models` into real retry/fallback execution path.

Implementation steps:
1. Scheduler payload: include `model` + `agent_config` in assignment payload.
2. Runtime extraction: resolve LLM params from payload in `agents/runtime_config.py`.
3. Agent callsites: pass resolved params in Worker/Manager/Orchestrator.
4. Decomposer path: propagate overrides into `task_decomposer.chat_json(...)`.
5. LLM path: consume `max_retries` and `fallback_models` in `llm_client._call_with_retry(...)` and fallback chain resolution.
6. Verification: add/extend unit tests for Worker/Manager/Orchestrator + llm_client + task_decomposer.

Acceptance:
- `max_retries` changes effective retry attempts for a call.
- `fallback_models` overrides default fallback order and de-duplicates invalid/self models.
- Missing overrides keep role-default model routing unchanged.
