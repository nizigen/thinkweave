# TECH_STACK.md — 技术栈文档

## 版本锁定原则
所有依赖必须锁定到精确版本号，禁止使用 `^` 或 `~` 浮动版本。

---

## 后端

| 类别 | 技术 | 版本 | 用途 |
|------|------|------|------|
| 语言 | Python | 3.13.0 | 主语言 |
| Web框架 | FastAPI | 0.115.0 | RESTful API + WebSocket |
| ASGI服务器 | Uvicorn | 0.30.6 | 异步服务器 |
| ORM | SQLAlchemy | 2.0.35 | 数据库操作 |
| 数据校验 | Pydantic | 2.9.2 | 请求/响应模型 |
| 数据库驱动 | asyncpg | 0.31.0 | PostgreSQL异步驱动 |
| 缓存/消息队列 | redis-py | 5.1.1 | Redis客户端（支持async） |
| LLM接口 | openai | 1.51.0 | OpenAI/DeepSeek API调用 |
| 环境变量 | python-dotenv | 1.0.1 | 加载.env配置 |
| 任务调度 | APScheduler | 3.10.4 | 定时任务（如超时检测） |
| 文档导出 | python-docx | 1.1.2 | 导出DOCX |
| PDF导出 | reportlab | 4.2.5 | 导出PDF（纯Python，Windows友好） |
| 数据库迁移 | alembic | 1.13.2 | 数据库Schema迁移管理 |
| Markdown解析 | markdown | 3.7 | Markdown转HTML |
| YAML解析 | pyyaml | 6.0.2 | 技能文件YAML frontmatter解析 |
| MCP客户端 | mcp | 1.6.0 | Model Context Protocol客户端SDK |
| 向量扩展 | pgvector | 0.3.6 | PostgreSQL向量搜索（RAG检索模块用，pgvector-python绑定） |
| 记忆层框架 | cognee | 0.5.5 | Graph+Vector 混合记忆引擎（add/search/cognify API） |
| 图后端默认 provider | kuzu | current via cognee | 当前环境下 `cognee==0.5.5` 的默认图后端 |
| 向量后端默认 provider | lancedb | current via cognee | 当前环境下 `cognee==0.5.5` 的默认向量后端 |
| 日志 | loguru | 0.7.2 | 结构化日志 |

> **cognee 作为 pip 依赖引入**（`pip install cognee==0.5.5`）。通过薄适配层封装 `cognee` 的 `add()`/`search()`/`cognify()` API，对接项目的 `MemoryConfig`。默认 provider 为 `graph=kuzu`、`vector=lancedb`（cognee 内置默认）。支持的 graph 后端：kuzu / falkor / neo4j_aura_dev；支持的 vector 后端：lancedb / falkor / pgvector。不受支持的组合会显式报错。Windows 原生支持，无需 Docker。
| 测试 | pytest | 8.3.3 | 单元测试 |
| 测试异步 | pytest-asyncio | 0.24.0 | 异步测试支持 |

---

## 前端

| 类别 | 技术 | 版本 | 用途 |
|------|------|------|------|
| 语言 | TypeScript | 5.6.2 | 主语言 |
| 框架 | React | 18.3.1 | UI框架 |
| 构建工具 | Vite | 5.4.8 | 开发服务器+打包 |
| UI组件库 | Ant Design | 5.21.0 | 基础UI组件 |
| 图形可视化 | @antv/g6 | 5.0.18 | DAG图绘制（G6图引擎） |
| 状态管理 | Zustand | 4.5.5 | 轻量全局状态 |
| 路由 | React Router | 6.27.0 | 页面路由 |
| HTTP客户端 | Axios | 1.7.7 | API请求 |
| WebSocket | 原生WebSocket | — | 实时状态推送 |
| Markdown渲染 | react-markdown | 9.0.1 | 文档渲染 |
| 代码高亮 | react-syntax-highlighter | 15.5.0 | 代码块高亮 |
| 动画 | framer-motion | 11.11.1 | 页面过渡动画 |
| 拖拽 | @dnd-kit/core | 6.1.0 | 大纲编辑器拖拽排序 |
| 拖拽排序 | @dnd-kit/sortable | 8.0.0 | 树形节点排序 |
| 图标 | @ant-design/icons | 5.5.1 | 图标库 |
| 类型检查 | @types/react | 18.3.11 | React类型定义 |
| 前端测试 | Vitest | 4.1.1 | Hook/store 单元测试 |
| React测试工具 | @testing-library/react | 16.3.2 | Hook 渲染与交互断言 |
| DOM断言扩展 | @testing-library/jest-dom | 6.9.1 | DOM 环境断言扩展 |
| DOM测试环境 | jsdom | 29.0.1 | 浏览器 API 模拟环境 |

---

## 数据库

| 技术 | 版本 | 用途 |
|------|------|------|
| PostgreSQL | 15.8 | 持久化存储（任务/Agent/消息历史）+ pgvector RAG检索 |
| Redis | 7.4.0 | 消息队列（Streams Consumer Group）+ 状态缓存（Hash/Sorted Set） |
| Kuzu | via cognee | 记忆层默认图后端（SessionMemory / promotion handoff） |
| LanceDB | via cognee | 记忆层默认向量后端（章节摘要、语义去重、相似检索） |

> **RAG vs Memory 职责分离**：pgvector 服务于 RAG 检索模块（文档分块检索）；`cognee` 管理的 memory provider 服务于章节级去重、会话记忆和后续知识提升。两者关注点不同，不合并。

---

## 基础设施

| 技术 | 版本 | 用途 |
|------|------|------|
| Docker | 27.3.1 | 容器化 |
| Docker Compose | 2.29.7 | 多容器编排 |
| Git | 2.46.0 | 版本控制 |

### 开发阶段 Docker 服务

Docker Compose 启动以下服务（backend/frontend 本地直接运行）：

| 服务 | 镜像 | 端口 | 用途 |
|------|------|------|------|
| PostgreSQL | ankane/pgvector:pg15 | 15432 | 数据库 + pgvector |
| Redis | redis:7.4 | 6379 | 消息队列 + 缓存 |
| Kuzu/LanceDB | provider-managed | local provider paths | 记忆层默认 graph/vector backend（由 `cognee==0.5.5` 管理） |


---

## 外部API

| 服务 | 模型 | 用途 |
|------|------|------|
| OpenAI API | gpt-4o | 高质量任务分解、审查评估 |
| DeepSeek API | deepseek-chat (V3.2) | 内容生成、协调调度，成本更低 |

API Key通过 `.env` 文件注入，禁止硬编码。

### LLM降级策略

当主模型不可用（超时/额度耗尽/API错误）时，自动降级到备用模型，不影响用户生成流程：
- GPT-4o 不可用 → 自动降级到 deepseek-chat
- deepseek-chat 不可用 → 自动降级到 GPT-4o
- 降级逻辑在 `llm_client.py` 中统一处理，对上层Agent透明

### 模型分配策略

不同Agent角色使用不同模型，在 `llm_client.py` 中通过角色映射配置：

| Agent角色 | 推荐模型 | 原因 |
|-----------|----------|------|
| Orchestrator（任务分解） | gpt-4o | 需要强推理能力进行任务拆解和DAG生成 |
| Manager（协调调度） | deepseek-chat | 协调逻辑相对简单，成本更低 |
| Outline Agent（大纲生成） | gpt-4o | 需要好的结构规划能力 |
| Writer Agent（内容撰写） | deepseek-chat | 写作质量好且成本低，适合批量并行调用 |
| Reviewer Agent（质量审查） | gpt-4o | 需要严谨的批判性思维进行评分 |
| Consistency Agent（一致性） | gpt-4o | 需要跨章节理解和对比能力 |

---

## 数据库Schema（主要表）

```sql
-- Agent注册表
agents (id, name, role, layer, capabilities, model, status, created_at)

-- 任务主表
tasks (id, title, mode, status, created_at, finished_at, output_text)

-- 子任务DAG节点
task_nodes (id, task_id, title, assigned_agent_id, status, depends_on[], result, started_at, finished_at)

-- 消息记录
messages (id, task_id, from_agent, to_agent, content, msg_type, created_at)
```

---

## 开发环境要求

```
操作系统：Windows 11 / Ubuntu 22.04 LTS
Python：3.13.0（建议使用 conda 管理环境）
Node.js：20.18.0 LTS
Docker Desktop：4.34.0+（仅用于运行PostgreSQL和Redis）
内存：≥16GB（同时运行多个LLM API调用）

开发模式：
- Docker Compose 只启动 PostgreSQL + Redis
- backend（FastAPI）本地直接运行：uvicorn app.main:app --reload
- frontend（Vite）本地直接运行：npm run dev
- 部署阶段再考虑全容器化
```

---

## 禁止引入的依赖

- 不使用 LangChain / LlamaIndex（自研编排逻辑，避免框架黑盒）
- 不使用 Celery（用 Redis + 自研调度替代）
- 不使用 GraphQL（REST已够用）

## 参考仓库能力映射（2026-03-21）

### 1. Prompt 工程增强
1. 审查 Prompt 采用结构化评分输出：`score_total` + `score_dimensions` + `must_fix`。
2. 修订 Prompt 采用固定回执结构：`changes_made` + `evidence_links` + `residual_risks`。
3. 一致性 Prompt 采用 claim 级检查对象：`claim_id` + `status` + `source`。

### 2. 技能注入机制增强
1. 注入粒度从“按角色”提升为“按阶段 + 角色”。
2. 在 `agent_config` 中新增可选字段（建议）：
   - `stage_skill_profile`
   - `review_rubric`
   - `integrity_policy`
3. 注入顺序固定并可审计：基础 system -> 角色 system -> 阶段 skill -> 当前任务约束。

### 3. 成本与稳定性约束
1. 复审/重验循环必须设置轮次上限，避免 token 失控。
2. Checkpoint 降噪策略：连续自动继续时切换 SLIM 展示。
3. 关键关卡（integrity/review decision）永远使用 MANDATORY，不允许跳过。
4. 审查与完整性报告统一 JSON Schema，便于自动评估与回归测试。
