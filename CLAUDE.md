# CLAUDE.md — 项目 AI 操作手册

## 项目信息
- **项目名称**：层级化Agent编排与长文本控制系统
- **目录**：`E:\claude\hierarch\`
---

## 规范文档索引（文档第一，代码第二）

| 文档 | 用途 | 缺失后果 |
|------|------|----------|
| `PRD.md` | 产品需求：功能范围、竞品分析、验收标准 | AI会幻觉需求 |
| `APP_FLOW.md` | 用户旅程：页面流、导航路径、交互细节 | AI会猜测用户行为 |
| `TECH_STACK.md` | 技术栈：所有依赖锁定到精确版本号 | AI会引入随机依赖 |
| `FRONTEND_GUIDELINES.md` | 前端设计系统：颜色/字体/间距/组件/动效 | UI零一致性 |
| `BACKEND_STRUCTURE.md` | 后端架构：目录结构/API/数据库Schema/服务设计 | AI会自行假设数据结构 |
| `IMPLEMENTATION_PLAN.md` | 实施计划：7个Phase的逐步构建序列 | AI会乱序构建或跳步骤 |

---

## 会话启动协议

每次会话开始时必须：
1. 读取 `CLAUDE.md`、`progress.txt`、`lessons.md`
2. 审查相关规范文档
3. 确认当前进度和接下来的任务
4. 按照 `IMPLEMENTATION_PLAN.md` 确定当前 Step，只做这一步

---

## 核心架构约束

### 三层Agent架构
- **Layer 0 编排层**：Orchestrator Agent，负责任务分解和全局协调
- **Layer 1 管理层**：Manager Agent（单一基类，通过角色配置区分策略规划/资源调度/质量控制职责）
- **Layer 2 执行层**：Outline / Writer / Reviewer / Consistency Agent

### Agent生命周期
- Agent注册 = 数据库定义（名称、角色、层级、能力、模型配置）
- 系统按需实例化Agent协程（在FastAPI进程内以asyncio协程运行）
- 心跳机制用于监控Agent活性（即使是协程也需要心跳，用于超时检测和状态报告）
- Agent状态：idle → busy → idle / offline

### 通信机制
- **Redis Streams**（Consumer Group模式）用于Agent间消息传递，**绝对不用Pub/Sub**
- Redis Sorted Set 用于优先级调度和超时监控
- Redis Hash 用于Agent状态和DAG状态快照
- 消息持久化到PostgreSQL messages表

### 长文本写作模式（并行写作 + 一致性修正）
核心流程：
1. **大纲Agent** 生成章节结构，每章设计为尽量独立（明确章节边界和衔接要点）
2. **写作Agent（多实例）并行撰写**各章节，每个Writer拿到完整大纲 + 自己负责的章节
3. **审查Agent** 对每章独立评分（≥70分通过，<70分退回重写，最多3次）
4. **一致性Agent** 全文扫描，**指出跨章节问题**（风格不统一、逻辑矛盾、重复内容），将问题清单发给对应写作Agent修改
5. 写作Agent完成修改后，一致性Agent再次检查，最多循环2次

### 长文本FSM状态机
```
INIT → OUTLINE → OUTLINE_REVIEW → WRITING → REVIEWING → CONSISTENCY → DONE
                                     ↑___________|（审查不通过回写作，最多3次）
                                     ↑__________________________|（一致性不通过回写作，最多2次）
```

### 模型分配策略
| Agent角色 | 推荐模型 | 原因 |
|-----------|----------|------|
| Orchestrator（任务分解） | GPT-4o | 需要强推理能力进行任务拆解 |
| Manager（协调调度） | DeepSeek-V3.2 | 协调逻辑相对简单，成本更低 |
| Outline Agent（大纲生成） | GPT-4o | 需要好的结构规划能力 |
| Writer Agent（内容撰写） | DeepSeek-V3.2 | 写作质量好且成本低，适合批量调用 |
| Reviewer Agent（质量审查） | GPT-4o | 需要严谨的批判性思维 |
| Consistency Agent（一致性） | GPT-4o | 需要跨章节理解和对比能力 |

所有模型调用通过 `utils/llm_client.py` 统一适配层，**禁止直接 import openai**。

---

## 编码规则

### 后端（Python）
- 使用 FastAPI + asyncpg + SQLAlchemy 2.0 async
- 所有数据库操作使用 async/await
- Pydantic v2 用于请求/响应校验
- loguru 替代 logging
- 所有 LLM 调用通过 `utils/llm_client.py` 统一适配层
- Immutable patterns：always spread/create new objects, never mutate
- 函数 < 50 行，文件 200-400 行（最大800行）

### 前端（TypeScript + React）
- React 18 + Vite + TypeScript strict mode
- Ant Design 5 暗色主题（主色 #6366F1）
- Zustand 状态管理（不用 Redux）
- @antv/g6 v5 绘制DAG图
- framer-motion 处理动画
- 原生 WebSocket（不用 socket.io）
- UI state must derive from core data, not external temp state

### 禁止项
- 不使用 LangChain / LlamaIndex（自研编排）
- 不使用 Celery（自研Redis调度）
- 不使用 GraphQL（REST够用）
- 不使用 jQuery 动画
- 不使用 socket.io
- 不使用 Redis Pub/Sub（用 Streams）
- 不补丁式修复（必须理解整体设计后再改）
- 不吞异常（no empty catch blocks）
- 不猜接口行为（先读文档/源码）
- 不在没有明确需求时实现功能（先和用户确认）

---

## 文件约定
- 后端代码：`backend/app/`
- 前端代码：`frontend/src/`
- 数据库迁移：`backend/migrations/`（Alembic）
- 测试：`backend/tests/`、`frontend/src/__tests__/`
- 环境变量：`.env`（不提交git），`.env.example`（提交）

## 工作流强制执行

### 构建期间
1. 小碎片工作，一次一个功能
2. 引用规范文档的具体章节："按照 FRONTEND_GUIDELINES.md 第2节样式化"
3. 每个有效功能后提交到 git
4. **每个功能后立即更新 progress.txt**
5. 每次纠正后更新 CLAUDE.md 和 lessons.md

### 实施计划引用
```
构建 IMPLEMENTATION_PLAN.md 的步骤 X.X
只构建这个步骤。不要跳到前面。
```

### 技术栈约束
```
只使用 TECH_STACK.md 中列出的包。
没有询问不要添加新依赖。
```

### 调试循环
1. 读错误。真的读它
2. 找到位置：什么文件，什么行
3. 理解声明：错误说什么是错的？
4. 检查明显的：拼写错误、缺失导入、错误的变量名
5. 给 AI 上下文：错误 + 代码 + 你期望什么
6. 卡住2-3轮后 → 切换方法，不要暴力重试

## Git 提交格式
```
<type>: <description>
```
type: feat | fix | refactor | docs | test | chore | perf | ci

## 进度追踪
每完成一个 Step 后立即更新 `progress.txt`。
每完成一个 Step 后，同时在 `IMPLEMENTATION_PLAN.md` 中将对应的 `- [ ]` 改为 `- [x]`。

## 自我改进
每次 AI 犯错被用户纠正时，立即在此文件添加新规则防止再犯。

---

## 关键决策记录

| 决策 | 结论 | 日期 |
|------|------|------|
| 参考资料上传 | v1不做，用户在prompt中描述即可 | 2026-03-06 |
| 自定义生成模式 | 预设模板 + 自由描述两种方式 | 2026-03-06 |
| 研究深度 | 同时控制DAG粒度和生成字数（快速3k/标准10k/深入20k） | 2026-03-06 |
| 大纲编辑器 | @dnd-kit 拖拽库 + 自定义树组件 | 2026-03-06 |
| PDF导出 | reportlab（纯Python，Windows友好），不用weasyprint | 2026-03-06 |
| LLM降级 | 主模型不可用时自动fallback到备用模型 | 2026-03-06 |
| Docker策略 | 开发阶段Docker只跑PostgreSQL+Redis，backend/frontend本地运行 | 2026-03-06 |
| DeerFlow参考 | 借鉴中间件模式/并发控制/输入验证/Token追踪/模型配置化，不引入LangChain | 2026-03-07 |
| MCP + Skills | Agent支持MCP工具调用（客户端模式）+ Skills系统（写作风格模板+Agent行为定义，Markdown+YAML frontmatter） | 2026-03-07 |
| 上下文管理 | 三层记忆（Working/Task/Persistent）+ 渐进式披露 + 上下文压缩，参考OpenClaw+claude-mem | 2026-03-07 |
| Prompt缓存 | 利用OpenAI/DeepSeek自动前缀缓存（静态在前变量在后），不做应用层语义缓存 | 2026-03-07 |
| 向量数据库 | pgvector（复用PG，零新基础设施），嵌入模型text-embedding-3-small | 2026-03-07 |
| RAG策略 | v1实现轻量RAG（跨章节检索+一致性检查），rag_enabled默认关闭；用户文档上传推迟到v2 | 2026-03-07 |
| Prompt模板 | 文件化管理（prompts/{role}/{action}.md），str.format_map渲染，不引入Jinja2 | 2026-03-07 |
| 结构化日志 | loguru + logger.bind(task_id, agent_id, role)，多Agent并发日志关联 | 2026-03-07 |
| 错误恢复 | FSM检查点机制（checkpoint_data JSONB），崩溃后resume()恢复，不重置重试计数 | 2026-03-07 |
| 测试策略 | BaseLLMClient ABC + MockLLMClient依赖注入，fakeredis替代Redis，测试不调外部API | 2026-03-07 |

## 纠错记录
（随项目推进动态添加）

---

## 开发模式强制规则

### 前端开发
- **必须使用 `/ui-ux-pro-max`以及`/frontend-design` 技能进行 UI/UX 指导**
- 每次前端页面开发前，**必须要求用户提供参考网页/截图**作为设计基准
- 没有参考网页不开始前端 UI 编码（技术基础设施除外）
- 参考网页用于指导布局、交互、视觉风格，结合 FRONTEND_GUIDELINES.md 确保一致性

### 后端开发
- **使用 `everything claude code` 技能或 `omc`（oh-my-claudecode）编排完成后端开发**
- 利用 omc 的多 Agent 协作能力进行复杂后端实现
- 后端代码变更后必须通过 code-reviewer / security-reviewer 审查
