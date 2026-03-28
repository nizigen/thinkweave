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
- [x] 画出 3 个 API 的 import 依赖链 → **结论：vendor 源码方式依赖链过深（>3000 LOC，35+ 核心依赖）**
- [x] 评估 `cognify()` 实体提取 → **可用 `llm_client.chat_json()` 完全替代**（cognee 内部也是 LLM 结构化输出）
- [x] **最终方案**：不 vendor cognee 源码，改为 `pip install cognee==0.5.5` 使用其 API，封装薄适配层
- [x] 产出 spike 报告，更新 TECH_STACK.md + Step 4.1b

### Step 4.1b — 记忆层基础设施（pip install cognee==0.5.5 + 薄适配层）
- [x] `pip install cognee==0.5.5` 到项目 venv，验证基础 import 和 `add()`/`search()`/`cognify()` 可调用
- [x] cognee 默认 provider（kuzu + lancedb）开箱即用，无需额外 Docker 服务
- [x] 实现 `memory/config.py`（MemoryConfig，pydantic-settings，MEMORY_ENABLED 开关，graph/vector provider 可配置）
- [x] 实现 `memory/adapter.py`（cognee 薄适配层：封装 cognee.add/search/cognify，白名单校验 provider 组合）
- [x] 实现 `memory/models.py`（TopicClaim / ContentSummary / EntityRelation 等项目侧数据模型）
- [x] 实现 `memory/embedding.py`（复用 llm_client.embed()，带 SHA256 内容哈希缓存）
- [x] 实现 `memory/image_registry.py`（图片 URL→章节映射，asyncio.Lock 防跨章节重复）
- [x] 实现 `memory/session.py`（SessionMemory 统一 API：initialize/store/query/cleanup，namespace 隔离，内部调用 cognee adapter）
- [x] 实现优雅降级（MEMORY_ENABLED=false 跳过所有 cognee 调用，provider 不可用时显式报错）
- [x] 单元测试（FakeCogneeClient mock，测试适配层和 SessionMemory 逻辑，10 测试全通过）

### Step 4.2 — 专用Agent实现（含记忆集成）
- [x] 实现 `outline_agent.py`（生成Markdown大纲，包含 context bridges + **topic_claims**：每章 owns + boundary）
- [x] 实现 `writer_agent.py`（基于完整大纲+章节描述并行写作，**启动前从 Session Memory 读取其他章节摘要**）
- [x] 实现 `reviewer_agent.py`（对每章评分0-100，≥70通过，**审查时检测内容重叠**）
- [x] 实现 `consistency_agent.py`（全文扫描，**从 Session Memory 读取章节摘要而非全文**，降低 token 消耗）
- [x] 实现 `MemoryMiddleware`（记忆层中间件：before_task 注入去重指令，after_task 写入摘要）
- [x] 更新 Outline prompt 模板（`prompts/outline/generate.md`）：要求输出 topic_claims 字段
- [x] 更新 Writer prompt 模板（`prompts/writer/write_chapter.md`）：增加 `{memory_context}` 占位符
- [x] 更新 Reviewer prompt 模板：增加重叠检测结果注入

### Step 4.3 — 长文本生成流程集成（含记忆生命周期）
- [x] FSM 进入 OUTLINE 状态时：**初始化 SessionMemory**（创建 session 命名空间）
- [x] FSM 进入 OUTLINE 后：大纲生成后，**topic_claims 写入 SessionMemory.store_territory_map()**
- [x] 大纲生成后进入OUTLINE_REVIEW，等待用户确认/编辑
- [x] 写作Agent并行执行，每个Writer拿到完整大纲+自己的章节+**Session Memory 去重上下文**
- [x] 审查不通过（<70分）或检测到重叠 → 回到WRITING状态对应章节重写（最多3次）
- [x] 一致性不通过 → 问题清单发给对应Writer修改（最多2次循环）
- [x] FSM 进入 DONE 时：**SessionMemory.cleanup()（可选提升数据到 Knowledge Graph）**
- [x] 各章节文本拼接为完整文档
- [x] 更新 tasks.output_text + tasks.word_count
- [x] 检查点数据中包含 session_memory_id，崩溃恢复时可重新挂载
- [x] 实现 `evaluate_dedup_quality(task_id)` 度量脚本：计算所有章节对的向量相似度，>0.85 判定为重复，输出重复率报告
- [x] 基线测试：关闭记忆层生成一篇报告 → 跑度量脚本得基线；启用记忆层再生成 → 对比（目标 < 5%）

### Step 4.4 — Knowledge Graph（跨任务知识积累）
- [x] 实现 `memory/knowledge/graph.py`（KnowledgeGraph：持久化查询/存储 API）
- [x] 实现 `memory/knowledge/promotion.py`（Session→KG 数据提升：已验证引用、实体关系、术语定义）
- [x] 任务完成时 SessionMemory.cleanup() 自动触发 promote（credibility ≥ 0.7 的数据提升到 KG）
- [x] Outline/Writer Agent 启动前查询 KG 历史知识（通过 MemoryMiddleware.before_task）
- [x] KG 条目 90 天 TTL（stale 后需重新验证）
- [x] 集成测试（跨任务知识复用场景）

**验收：** 输入"写一篇量子计算技术报告"，系统输出≥8000字的结构化文档；并行章节内容重复率 < 5%（对比无记忆层的 20-30%）；第二次生成同主题报告时，能复用首次验证的引用和实体关系

---

## Phase 5：实时监控 + WebSocket（第10周）

### Step 5.1 — WebSocket 后端基础设施
- [x] 实现 `routers/ws.py`：`/ws/task/{task_id}` WebSocket 端点，FastAPI WebSocket 路由
- [x] 实现连接管理器 `services/ws_manager.py`：维护 task_id → WebSocket 连接集合的映射，支持多客户端同时订阅同一任务
- [x] 实现 `connect(task_id, ws)` / `disconnect(task_id, ws)` / `broadcast(task_id, message)` 三个核心方法
- [x] 心跳机制：每 30 秒发送 ping，客户端 60 秒无 pong 断开
- [x] 连接鉴权：WebSocket 握手时校验 task_id 是否存在（404 拒绝连接）

### Step 5.2 — Redis→WebSocket 事件桥接
- [x] 实现 `services/event_bridge.py`：后台 asyncio task，XREAD `task:{task_id}:events` 流
- [x] 消息类型定义（Pydantic 模型）：`node_update` / `log` / `agent_status` / `task_done` / `chapter_preview` / `review_score` / `consistency_result` / `dag_update`
- [x] 每条 Redis event 解析后通过 `ws_manager.broadcast(task_id, msg)` 推送给所有订阅客户端
- [x] 事件桥接生命周期：首个客户端连接时启动 XREAD，最后一个客户端断开时停止
- [x] 单元测试：mock Redis stream，验证消息正确转发到 WebSocket

### Step 5.3 — Agent 侧事件发射
- [x] 在 `LoggingMiddleware` 中，每次 Agent 开始/完成任务时，XADD `node_update` 事件到 `task:{task_id}:events`
- [x] 在 Writer Agent 写作过程中，定期 XADD `chapter_preview` 事件（每 500 字或每段落）
- [x] 在 Reviewer Agent 评分后，XADD `review_score` 事件
- [x] 在 Consistency Agent 检查后，XADD `consistency_result` 事件
- [x] FSM 状态转换时，XADD `dag_update` 事件（节点状态变更）
- [x] 任务完成/失败时，XADD `task_done` 事件
- [x] 双审查回补硬化：
  - WebSocket 来源校验改为复用 `settings.cors_allow_origins`
  - ownerless task 默认拒绝非管理员订阅
  - query token 回退默认关闭，仅保留显式配置开关
  - `connected` 帧先于 bridge 启动发送
  - bridge 启动前先捕获当前 stream cursor，避免首批事件被 `$` 跳过
  - 新连接先进入 pending，待 `connected` 发出后再激活到广播集合
  - 超大客户端消息直接关闭连接
  - bridge 启停加锁，读取/广播失败支持退避重试
  - failed `node_update` 事件改为仅发送安全错误码与摘要
  - 失败 `node_update` 改为安全摘要，不再暴露原始异常

### Step 5.4 — 前端 WebSocket 连接层
- [x] 实现 `hooks/useTaskWebSocket.ts`：封装原生 WebSocket 连接，自动重连（指数退避，最多 5 次）
- [x] 消息分发：根据 `type` 字段路由到独立的 `monitorStore` action，并忽略跨任务/过期 socket 事件
- [x] 连接状态管理：`connecting` / `connected` / `disconnected` / `error`，`Monitor` 页面显示连接指示器
- [x] 断线重连后，通过 REST API `GET /api/tasks/{id}` 拉取最新状态做一次全量同步
- [x] 单元测试：mock WebSocket，验证消息分发、任务切换竞态保护、终止性 close code 和重连逻辑

### Step 5.5 — 前端 DAG 实时可视化
- [x] 实现 `components/DagViewer.tsx`：@antv/g6 v5 初始化，从 task nodes 数据渲染 DAG 图
- [x] 节点颜色映射：pending(灰) → running(蓝+边框发光动画) → completed(绿) → failed(红)
- [x] 边样式：已完成依赖(实线) / 待执行依赖(虚线)
- [x] 接收 `node_update` 消息后，实时更新对应节点颜色和状态标签
- [x] 接收 `dag_update` 消息后，动态增删节点和边（支持 FSM 驱动的动态 DAG 变更）
- [x] 布局算法：dagre 分层布局，节点可拖拽调整位置
- [x] 节点点击弹出详情面板（Agent 名称、开始时间、耗时、输出摘要）

### Step 5.6 — 前端监控面板组件
- [x] 实现 `pages/TaskMonitor.tsx` 页面布局：左侧 DAG 图（70%宽）+ 右侧面板（30%宽）
- [x] 右上：Agent 活动面板 `components/AgentPanel.tsx`（当前活跃 Agent 列表，每个 Agent 显示角色/状态/当前任务）
- [x] 右下：执行日志流 `components/LogStream.tsx`（接收 `log` 消息，自动滚动，支持按 Agent 过滤，最多保留 500 条）
- [x] 顶部：FSM 进度条 `components/FsmProgress.tsx`（显示当前 FSM 阶段，已完成阶段打勾）
- [x] 实时预览面板 `components/ChapterPreview.tsx`：接收 `chapter_preview` 消息，Markdown 渲染，按章节 tab 切换
- [x] 审查评分显示：接收 `review_score` 后在对应章节 tab 上显示分数徽标
- [x] 响应式布局：窄屏时右侧面板折叠为底部 tab

**验收：** 运行长文本任务时，前端 DAG 节点实时变色（≤2秒延迟），日志实时滚动，章节预览实时追加，断线重连后自动恢复状态

---

## Phase 6：结果展示 + 导出（第10-11周）

### Step 6.1 — 导出服务后端（高质量排版方案）

> **方案决策（2026-03-30）**：放弃 reportlab/python-docx 自行排版方案，改用 **Pandoc + XeLaTeX** 流水线。
> 原因：reportlab 的中文排版质量差（字体嵌入、行距、标题层级均需大量手工调整），python-docx 样式控制繁琐。
> Pandoc + XeLaTeX 可输出出版级 PDF，Pandoc + reference.docx 可输出完全符合 Word 样式规范的 DOCX。

#### 依赖安装
```bash
apt-get install -y pandoc texlive-xetex texlive-fonts-recommended texlive-lang-chinese fonts-noto-cjk
```

#### PDF 输出（XeLaTeX 引擎）
- 字体：正文 Noto Serif CJK SC，标题 Noto Sans CJK SC
- 行距 1.5，页边距 2.5cm，A4 纸
- 自动生成目录（`\tableofcontents`）
- 代码块语法高亮（minted 宏包）
- 彩色超链接
- 页眉页脚：章节名 + 页码

```python
# services/exporter.py
import subprocess, tempfile, os

class PdfExporter(BaseExporter):
    def export(self, title: str, markdown_text: str) -> bytes:
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = os.path.join(tmpdir, 'input.md')
            pdf_path = os.path.join(tmpdir, 'output.pdf')
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(f'---\ntitle: "{title}"\nauthor: "Hierarch"\ndate: "{date.today()}"\n---\n\n')
                f.write(markdown_text)
            subprocess.run([
                'pandoc', md_path, '-o', pdf_path,
                '--pdf-engine=xelatex',
                '-V', 'mainfont=Noto Serif CJK SC',
                '-V', 'sansfont=Noto Sans CJK SC',
                '-V', 'monofont=Noto Sans Mono CJK SC',
                '-V', 'fontsize=12pt',
                '-V', 'geometry:margin=2.5cm',
                '-V', 'linestretch=1.5',
                '-V', 'colorlinks=true',
                '-V', 'linkcolor=NavyBlue',
                '--toc', '--toc-depth=3',
                '--highlight-style=tango',
            ], check=True)
            with open(pdf_path, 'rb') as f:
                return f.read()
```

#### DOCX 输出（reference.docx 模板）
- 通过自定义 `reference.docx` 控制所有样式（字体/颜色/标题层级/页眉页脚）
- 正文字体：微软雅黑 / Noto Sans CJK SC，12pt
- 标题：加粗，蓝色（#2E4057），自动编号
- 代码块：等宽字体，灰色背景

```python
class DocxExporter(BaseExporter):
    REFERENCE_DOCX = 'assets/reference.docx'  # 预制模板
    def export(self, title: str, markdown_text: str) -> bytes:
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = os.path.join(tmpdir, 'input.md')
            docx_path = os.path.join(tmpdir, 'output.docx')
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(markdown_text)
            subprocess.run([
                'pandoc', md_path, '-o', docx_path,
                f'--reference-doc={self.REFERENCE_DOCX}',
                '--toc',
            ], check=True)
            with open(docx_path, 'rb') as f:
                return f.read()
```

#### 实施步骤
- [ ] 安装 pandoc + texlive-xetex + fonts-noto-cjk
- [ ] 实现 `services/exporter.py` 基类 `BaseExporter`
- [ ] 实现 `PdfExporter`（Pandoc + XeLaTeX，Noto CJK 字体）
- [ ] 实现 `DocxExporter`（Pandoc + reference.docx 模板）
- [ ] 制作 `assets/reference.docx` 样式模板（标题/正文/代码块样式）
- [ ] 实现 `routers/export.py`：`GET /api/export/{task_id}/docx` 和 `GET /api/export/{task_id}/pdf`
- [ ] 导出文件命名规则：`{task_title}_{date}.docx/pdf`，中文文件名 URL 编码
- [ ] 错误处理：task 不存在 404，task 未完成 409
- [ ] 单元测试：mock task 数据，验证 Pandoc 调用参数和文件生成

### Step 6.2 — 前端结果展示页
- [x] 实现 `pages/TaskResult.tsx` 页面：从 `GET /api/tasks/{id}/result` 获取完成的任务数据
- [x] Markdown 渲染区：`react-markdown` + `react-syntax-highlighter` 代码高亮，支持表格/列表/引用
- [x] 左侧文档目录 `components/TableOfContents.tsx`：解析 Markdown 标题层级，生成锚点导航，滚动时高亮当前章节
- [x] 导出按钮组：DOCX / PDF 两个按钮，点击后 `window.open(/api/export/...)` 触发下载
- [x] 生成统计卡片：总字数、章节数、生成耗时、使用的 Agent 数、Token 消耗
- [x] 审查评分展示：每章节评分徽标（≥70 绿色，<70 红色）
- [x] 空状态/加载状态/错误状态处理

### Step 6.3 — 历史任务页
- [x] 实现 `pages/TaskHistory.tsx`：Ant Design Table 展示已完成任务列表
- [x] 列定义：任务标题、生成模式（技术报告/小说/自定义）、创建时间、完成时间、字数、状态
- [x] 搜索：按标题关键词模糊搜索（前端过滤 or 后端 `GET /api/tasks?search=xxx`）
- [x] 筛选：按状态（completed/failed/running）、按生成模式、按时间范围筛选
- [x] 排序：默认按创建时间倒序，支持点击列头切换排序
- [x] 分页：每页 20 条，Ant Design Pagination 组件
- [x] 行点击：跳转到 TaskResult 页面查看历史结果
- [x] 批量操作：多选 + 批量删除（确认弹窗）
- [x] 后端支持：`GET /api/tasks` 添加 `search`、`status`、`mode`、`offset`、`limit` 查询参数
- [x] 空状态：无历史任务时显示引导文案

### Step 6.4 — 任务创建页优化
- [x] 创建成功后自动跳转到 TaskMonitor 页面
- [x] 大纲确认交互：OUTLINE_REVIEW 状态时，前端展示可编辑大纲（Markdown 编辑器），用户确认后继续
- [x] 进度通知：任务完成时浏览器 Notification API 推送（需用户授权）

**验收：** 完整走通一次任务：创建 → 大纲确认 → 监控实时进度 → 查看结果 → 导出 DOCX/PDF → 在历史任务页找到并重新查看

---

## Phase 7：系统集成测试 + 收尾（第11周）

### Step 7.1 — 端到端测试用例
- [x] E2E 测试：技术报告生成完整流程（创建 → 大纲 → 写作 → 审查 → 一致性 → 完成），验证输出≥8000字、结构完整
- [x] E2E 测试：小说写作完整流程（创建 → 大纲 → 并行章节写作 → 审查 → 一致性 → 完成），验证叙事连贯
- [x] E2E 测试：自定义模式流程（用户自定义 prompt → 生成），验证自定义 prompt 正确注入
- [x] E2E 测试：草稿续写/评论修改入口（draft_text / review_comments → 跳过大纲直接进入 PRE_REVIEW_INTEGRITY）

### Step 7.2 — 故障恢复与边界测试
- [x] Agent 超时恢复测试：模拟 Writer Agent 超时（心跳丢失），验证系统自动重试或标记失败
- [x] FSM 检查点恢复测试：任务执行到 WRITING 阶段时模拟进程崩溃，重启后 `scan_and_resume_running_tasks()` 恢复执行
- [x] LLM 降级测试：主模型 API 返回 429/500，验证自动 fallback 到备用模型
- [x] Redis 断连恢复测试：临时断开 Redis，验证重连后消息不丢失（Consumer Group ACK 机制）
- [x] 审查重试上限测试：章节连续 3 次审查不通过（<70分），验证 FSM 正确转到 FAILED 状态
- [x] 一致性重试上限测试：一致性检查连续 2 次不通过，验证 FSM 正确处理

### Step 7.3 — WebSocket 与前端集成测试
- [x] WebSocket 断线重连测试：服务端主动断开连接，验证前端自动重连 + 全量状态同步
- [x] 多客户端订阅测试：两个浏览器 tab 同时监控同一任务，验证都能收到实时更新
- [x] 大量日志压力测试：快速生成 1000+ 条日志消息，验证前端 LogStream 不卡顿（虚拟滚动 or 截断）
- [x] DAG 动态更新测试：FSM 回退（审查不通过→重写）时，验证 DAG 节点状态正确回退

### Step 7.4 — 导出文件验证
- [x] DOCX 格式验证：用 python-docx 读回导出文件，验证标题层级、段落数、中文渲染正确
- [x] PDF 格式验证：用 PyPDF2 读回导出文件，验证页数合理、中文字体正确嵌入、页码连续
- [x] 大文件导出测试：≥20000 字文档导出，验证不超时（StreamingResponse 分块传输）
- [x] 特殊字符测试：包含代码块、表格、LaTeX 公式的文档导出，验证格式不丢失

### Step 7.5 — 性能与安全基线
- [x] 并发写作性能：5 个 Writer Agent 并行写作，验证总耗时 < 单 Agent 顺序写作的 2x
- [x] Token 消耗统计：一次完整技术报告生成的总 Token 消耗，记录基线（目标：input < 50k，output < 30k）
- [x] 记忆层去重效果：对比有/无记忆层的章节重复率（目标 < 5% vs 20-30%）
- [x] API 安全检查：确认所有端点有适当的输入校验（Pydantic），无 SQL 注入风险
- [x] 环境变量安全：确认 `.env` 在 `.gitignore`，前端代码无 API key 泄露

### Step 7.6 — 文档收尾
- [x] 更新 README.md：项目介绍、快速开始、架构图、API 文档链接
- [x] 更新 BACKEND_STRUCTURE.md：反映最终实现（如有偏差）
- [x] 更新 progress.md：标记所有 Phase 完成
- [x] 更新 IMPLEMENTATION_PLAN.md：所有 checkbox 标记完成
- [x] 编写部署指南：Docker Compose 一键启动（PostgreSQL + Redis + Backend + Frontend）
- [x] 编写 `.env.example`：所有必需环境变量及说明

**验收：** 所有 E2E 测试通过；故障恢复测试覆盖 Agent 超时、FSM 检查点、LLM 降级、Redis 断连场景；导出文件格式正确；并行章节重复率 < 5%；README 和部署指南完整可用
