# BACKEND_STRUCTURE.md — 后端架构规范

## 项目目录结构

```
backend/
├── app/
│   ├── main.py                 # FastAPI入口，注册路由、中间件
│   ├── config.py               # 配置读取（从.env）
│   ├── database.py             # PostgreSQL连接池（asyncpg）
│   ├── redis_client.py         # Redis连接（异步）
│   │
│   ├── models/                 # SQLAlchemy ORM模型
│   │   ├── agent.py            # Agent表
│   │   ├── task.py             # Task主表
│   │   ├── task_node.py        # 子任务节点表（DAG节点）
│   │   └── message.py          # 消息记录表
│   │
│   ├── schemas/                # Pydantic请求/响应模型
│   │   ├── agent.py
│   │   ├── task.py
│   │   └── message.py
│   │
│   ├── routers/                # API路由
│   │   ├── agents.py           # /api/agents
│   │   ├── tasks.py            # /api/tasks
│   │   ├── nodes.py            # /api/nodes
│   │   ├── export.py           # /api/export
│   │   └── ws.py               # WebSocket端点
│   │
│   ├── services/               # 业务逻辑层
│   │   ├── agent_manager.py    # Agent注册/状态管理
│   │   ├── task_decomposer.py  # LLM任务分解 → DAG
│   │   ├── dag_scheduler.py    # DAG调度引擎
│   │   ├── long_text_fsm.py    # 长文本FSM控制器
│   │   ├── communicator.py     # Redis消息收发
│   │   ├── exporter.py         # DOCX/PDF导出
│   │   ├── redis_streams.py    # Redis Streams封装（XADD/XREAD/consumer group）
│   │   ├── heartbeat.py        # Agent心跳管理（发送/检测/超时处理）
│   │   └── timeout_monitor.py  # 任务超时监控（Sorted Set轮询）
│   │
│   ├── agents/                 # Agent实现
│   │   ├── base_agent.py       # 抽象基类（含心跳、消息收发、生命周期、中间件钩子）
│   │   ├── middleware.py       # Agent中间件（日志/超时/重试/上下文摘要，参考DeerFlow模式）
│   │   ├── orchestrator.py     # 编排层Agent（Layer 0，任务分解+DAG生成）
│   │   ├── manager.py          # 管理层Agent（Layer 1，单一基类，通过role配置区分职责）
│   │   ├── outline_agent.py    # 大纲Agent（执行层，生成章节结构+context bridges+topic_claims主题领地）
│   │   ├── writer_agent.py     # 写作Agent（执行层，并行撰写章节，启动前从Session Memory读取去重上下文）
│   │   ├── reviewer_agent.py   # 审查Agent（执行层，评分0-100，含重叠检测）
│   │   ├── consistency_agent.py # 一致性Agent（执行层，从Session Memory读取章节摘要，指出问题→发回写作Agent）
│   │   └── agent_registry.py   # Agent注册表（维护能力索引，用于任务匹配）
│   │
│   ├── skills/                 # 技能系统
│   │   ├── loader.py           # 技能文件扫描和加载（从skills/目录）
│   │   ├── parser.py           # Markdown + YAML frontmatter 解析
│   │   └── types.py            # Skill / SkillConfig 数据模型
│   │
│   ├── mcp/                    # MCP客户端集成（Agent调用外部工具）
│   │   ├── client.py           # MCP客户端管理器（连接/断开/工具发现）
│   │   ├── registry.py         # 工具注册表（汇总所有已连接MCP服务器的工具列表）
│   │   └── config.py           # MCP服务器配置（从mcp_servers.json加载）
│   │
│   ├── rag/                     # RAG检索模块（可选，rag_enabled控制）
│   │   ├── __init__.py
│   │   ├── chunker.py           # 文本分块（章节级+段落级，含重叠窗口）
│   │   ├── embedder.py          # 嵌入服务（通过llm_client调用text-embedding-3-small）
│   │   └── retriever.py         # 混合检索（pgvector语义搜索 + PG全文搜索）
│   │
│   ├── memory/                   # 记忆层模块（pip install cognee + 薄适配层，memory_enabled控制）
│   │   ├── __init__.py
│   │   ├── config.py             # MemoryConfig（pydantic-settings，覆盖cognee自带配置）
│   │   ├── adapter.py            # cognee薄适配层（封装add/search/cognify，对接项目配置）
│   │   ├── session.py            # SessionMemory（单次任务记忆：主题领地/内容去重/图片去重）
│   │   ├── models.py             # 项目侧数据模型（TopicClaim/ContentSummary/EntityRelation等）
│   │   ├── image_registry.py     # 图片使用追踪（URL→章节映射，asyncio.Lock防跨章节重复）
│   │   ├── embedding.py          # 嵌入层（复用llm_client.embed()，带SHA256缓存）
│   │   └── knowledge/
│   │       ├── __init__.py
│   │       ├── graph.py          # KnowledgeGraph（跨任务持久知识图谱）
│   │       └── promotion.py      # Session→Knowledge数据提升逻辑
│   │
│   └── utils/
│       ├── llm_client.py       # LLM统一适配层（OpenAI/DeepSeek，含模型注册表+降级+重试）
│       ├── context_manager.py  # 上下文管理器（三层记忆+渐进式披露+上下文压缩）
│       ├── prompt_loader.py    # Prompt模板加载器（从prompts/目录读取Markdown模板）
│       ├── embedding.py        # 嵌入接口（统一调用，支持OpenAI text-embedding-3-small）
│       ├── token_tracker.py    # Token用量统计（按任务/Agent累计，用于成本监控）
│       └── logger.py           # loguru配置（含结构化字段绑定：task_id/agent_id）
│
├── prompts/                     # Prompt模板文件（Markdown，按角色+模式组织）
│   ├── orchestrator/
│   │   └── decompose.md         # 任务分解Prompt
│   ├── outline/
│   │   └── generate.md          # 大纲生成Prompt
│   ├── writer/
│   │   ├── write_chapter.md     # 章节撰写Prompt
│   │   └── revise_chapter.md    # 章节修改Prompt（基于审查反馈）
│   ├── reviewer/
│   │   └── review_chapter.md    # 章节审查Prompt（评分标准）
│   └── consistency/
│       └── check.md             # 一致性检查Prompt
│
├── skills/                      # 技能定义文件（Markdown，项目级）
│   ├── writing_styles/          # 写作风格技能
│   │   ├── technical_report.md  # 技术报告写作规范
│   │   ├── novel.md             # 小说写作规范
│   │   └── academic_paper.md    # 学术论文写作规范
│   ├── agent_behaviors/         # Agent行为技能
│   │   ├── researcher.md        # 深度研究型写作（先搜索后写作）
│   │   ├── creative_writer.md   # 创意写作（注重表达和节奏）
│   │   └── quality_reviewer.md  # 质量审查行为（评分标准、反馈格式）
│   └── custom/                  # 用户自定义技能
│
├── mcp_servers.json             # MCP服务器配置文件（不提交git）
├── mcp_servers.example.json     # MCP服务器配置示例
├── migrations/                  # 数据库迁移脚本（Alembic）
├── tests/                      # pytest测试
├── .env                        # 环境变量（不提交git）
├── .env.example                # 环境变量示例
├── requirements.txt            # 依赖锁定
└── Dockerfile
```

---

## API端点设计

### Agent管理 `/api/agents`

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/agents` | 获取所有Agent列表 |
| POST | `/api/agents` | 注册新Agent |
| GET | `/api/agents/{id}` | 获取Agent详情 |
| PATCH | `/api/agents/{id}/status` | 更新Agent状态 |
| DELETE | `/api/agents/{id}` | 删除Agent |

### 任务管理 `/api/tasks`

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/tasks` | 获取历史任务列表 |
| POST | `/api/tasks` | 创建新任务（触发分解+调度） |
| GET | `/api/tasks/{id}` | 获取任务详情（含DAG节点） |
| POST | `/api/tasks/{id}/cancel` | 取消任务 |
| GET | `/api/tasks/{id}/result` | 获取最终生成文本 |

### 导出 `/api/export`

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/export/{task_id}/docx` | 导出为DOCX（流式返回） |
| GET | `/api/export/{task_id}/pdf` | 导出为PDF（流式返回） |

### WebSocket `/ws`

| 路径 | 描述 |
|------|------|
| `/ws/task/{task_id}` | 订阅任务实时更新（节点状态/日志流） |

**WebSocket消息格式**：
```json
{
  "type": "node_update | log | task_done | agent_status",
  "data": {
    "node_id": "xxx",
    "status": "running",
    "agent": "writer_agent_1",
    "content": "...",
    "timestamp": "2026-03-05T12:00:00Z"
  }
}
```

**新增消息类型**：
```json
// 长文本实时预览
{"type": "chapter_preview", "data": {"chapter_index": 2, "content": "部分Markdown...", "progress": 0.6}}

// 审查评分
{"type": "review_score", "data": {"chapter_index": 1, "score": 85, "pass": true}}

// 一致性检查结果
{"type": "consistency_result", "data": {"issues": [{"chapter_index": 2, "problem": "...", "suggestion": "..."}], "pass": false}}

// DAG动态更新
{"type": "dag_update", "data": {"action": "add_node", "node": {...}}}
```

---

## 核心服务设计

### Redis通信架构（redis_streams.py + communicator.py）

通信中间件采用 Redis Streams + Sorted Set 混合架构：

```
# Redis Streams 通信通道
agent:{agent_id}:inbox     - 每个Agent的任务接收流（Consumer Group模式）
task:{task_id}:events      - 每个任务的事件流（WebSocket订阅转发）
system:logs                - 全局日志流

# Redis Sorted Set 调度
scheduler:ready_nodes      - 就绪节点队列（score=优先级）
scheduler:timeout_watch    - 超时监控（score=deadline_timestamp）

# Redis Hash 状态
agent:{agent_id}:state     - Agent当前状态（status/current_task/last_heartbeat）
task:{task_id}:dag_state   - DAG节点状态快照
```

消息结构化协议：
```json
{
  "msg_id": "uuid",
  "type": "task_assign | task_result | heartbeat | status_update",
  "from": "orchestrator_1",
  "to": "writer_agent_3",
  "task_id": "uuid",
  "node_id": "uuid",
  "payload": {},
  "timestamp": "2026-03-05T12:00:00Z",
  "ttl": 60
}
```

---

### LLM统一适配层（llm_client.py）— 参考DeerFlow ModelConfig

模型注册表采用配置驱动，运行时按角色+能力选择模型，新增模型不改业务代码：

```python
# 模型配置注册表（在config.py中定义）
MODEL_REGISTRY: dict[str, ModelConfig] = {
    "gpt-4o": ModelConfig(
        provider="openai",
        model="gpt-4o",
        supports_streaming=True,
        supports_json_mode=True,
        max_tokens=4096,
        fallback="deepseek-chat",        # 不可用时降级到备用模型
    ),
    "deepseek-chat": ModelConfig(
        provider="deepseek",
        model="deepseek-chat",
        supports_streaming=True,
        supports_json_mode=True,
        max_tokens=8192,
        fallback="gpt-4o",
    ),
}

# 角色→模型映射（可通过config覆盖）
ROLE_MODEL_MAP: dict[str, str] = {
    "orchestrator": "gpt-4o",
    "manager": "deepseek-chat",
    "outline": "gpt-4o",
    "writer": "deepseek-chat",
    "reviewer": "gpt-4o",
    "consistency": "gpt-4o",
}
```

核心接口：
```python
class LLMClient:
    async def chat(messages, model=None, role=None, ...) -> str:
        """普通对话，按role自动选模型，失败自动降级"""

    async def chat_stream(messages, model=None, role=None, ...) -> AsyncIterator[str]:
        """流式输出，yield每个token chunk"""

    async def chat_json(messages, model=None, role=None, schema=None) -> dict:
        """结构化JSON输出，带schema校验"""

    async def chat_with_tools(messages, tools, model=None, role=None) -> dict:
        """工具调用循环：发送→解析function_call→执行工具→回传结果→直到无工具调用"""

    async def embed(texts: list[str], model: str = "text-embedding-3-small") -> list[list[float]]:
        """文本嵌入，统一通过OpenAI SDK调用，支持批量"""
```

降级+重试策略：
- 每次调用最多重试3次（指数退避：1s → 2s → 4s）
- 3次失败后自动切换到 `fallback` 模型再试3次
- 两个模型都失败 → 抛出 `LLMUnavailableError`
- 每次调用记录 token 用量到 `TokenTracker`（按 task_id / agent_role 聚合）

---

### Prompt模板管理（prompt_loader.py）

所有LLM prompt从文件加载，禁止在业务代码中硬编码prompt字符串：

```python
class PromptLoader:
    """从 prompts/{role}/{action}.md 加载Prompt模板"""

    def __init__(self, prompts_dir: str = "prompts"):
        self.prompts_dir = Path(prompts_dir)
        self._cache: dict[str, str] = {}  # 运行时缓存，避免重复IO

    def load(self, role: str, action: str, **variables) -> str:
        """
        加载并渲染模板：
        1. 读取 prompts/{role}/{action}.md
        2. 用 str.format_map() 替换 {variable_name} 占位符
        3. 返回渲染后的完整prompt字符串

        示例: loader.load("writer", "write_chapter", outline=..., chapter_index=2)
        """

    def load_system(self, role: str) -> str:
        """加载 prompts/{role}/system.md 作为system message"""
```

模板文件格式（Markdown + 变量占位符）：
```markdown
# prompts/writer/write_chapter.md

你是一个专业的写作Agent，负责撰写章节内容。

## 任务
根据大纲撰写第 {chapter_index} 章：{chapter_title}

## 完整大纲（供参考）
{full_outline}

## 本章要求
{chapter_description}

## 衔接要点
{context_bridges}

## 跨章节协调（来自 Session Memory）
{memory_context}

## 输出要求
- 使用Markdown格式
- 字数目标：{target_words}字
- 确保与前后章节的衔接自然
```

设计原则：
- **纯字符串模板**：用Python `str.format_map()`，不引入Jinja2（TECH_STACK约束）
- **运行时缓存**：首次加载后缓存到内存，reload仅在debug模式下启用
- **类型安全**：缺少变量时抛出 `KeyError` 而非静默输出 `{xxx}`
- **可测试**：模板文件是纯文本，可直接在测试中mock

---

### 任务分解器（task_decomposer.py）

**输入验证**（参考DeerFlow CLARIFY → PLAN → ACT 模式）：
分解前先验证输入完整性，避免 LLM 在模糊需求上幻觉：

```python
async def validate_task_input(title: str, mode: str) -> ValidationResult:
    """
    检查任务描述是否足够具体：
    - 标题长度 >= 10字符
    - mode 是合法枚举值
    - 可选：调用LLM判断需求是否有歧义，返回澄清问题
    """

async def decompose_task(title: str, mode: str, depth: str = "standard") -> DAGGraph:
    """
    验证输入 → 调用LLM分解 → 解析DAG → 验证合法性
    """
    validation = await validate_task_input(title, mode)
    if not validation.ok:
        raise TaskValidationError(validation.issues)

    prompt = build_decompose_prompt(title, mode, depth)
    response = await llm_client.chat_json(
        messages=[{"role": "user", "content": prompt}],
        role="orchestrator",
        schema=DAG_JSON_SCHEMA,
    )
    dag = parse_dag_from_json(response)
    validate_dag_acyclic(dag)
    return dag
```

LLM输出格式约束（JSON Schema）：
```json
{
  "nodes": [
    {
      "id": "node_1",
      "title": "生成技术报告大纲",
      "agent_role": "outline",
      "depends_on": []
    },
    {
      "id": "node_2",
      "title": "撰写第一章：背景介绍",
      "agent_role": "writer",
      "depends_on": ["node_1"]
    }
  ]
}
```

### DAG调度引擎（dag_scheduler.py）

**并发控制**（参考DeerFlow max_concurrent_subagents）：
```python
# 调度器配置常量
MAX_CONCURRENT_LLM_CALLS = 5     # 同时运行的LLM调用上限（防API限流）
MAX_CONCURRENT_WRITERS = 3       # 并行写作Agent上限（控制成本）
```
超出上限的就绪节点排队等待，调度器每轮只分配到上限为止。

调度逻辑：
1. 找出所有前置依赖已完成的节点（可执行集合）
2. 从空闲Agent中匹配能力最符合的Agent
3. 发送任务消息给Agent，修改节点状态为 `running`
4. 监听Redis响应，收到结果后标记完成，触发下一轮调度

调度器核心循环（每秒执行一次）：
```python
class DAGScheduler:
    async def run_loop(self):
        while True:
            # 1. 检查超时任务（Redis ZRANGEBYSCORE）
            await self._check_timeouts()
            # 2. 收集已完成节点的结果（Redis XREAD consumer group）
            await self._collect_results()
            # 3. 更新DAG状态，计算新的就绪节点
            ready = await self._compute_ready_nodes()
            # 4. 匹配Agent并分配任务
            for node in ready:
                agent = await self._match_agent(node)
                if agent:
                    await self._assign_task(agent, node)
                    # 设置超时监控
                    await redis.zadd("scheduler:timeout_watch",
                        {node.id: time.time() + 60})
            await asyncio.sleep(1)

    async def schedule(self, dag: DAGGraph):
        while not dag.is_complete():
            ready_nodes = dag.get_ready_nodes()
            for node in ready_nodes:
                agent = await agent_manager.get_available_agent(node.agent_role)
                await communicator.assign_task(agent, node)
```

**Agent匹配策略**：
- 首先按角色（role）过滤
- 然后按负载排序（当前任务数最少优先）
- 最后检查心跳（最近30s内有心跳的才视为可用）

**失败恢复机制**：
- Agent心跳超时（30s无心跳）→ 标记Agent为offline → 其任务回到就绪队列
- 节点执行超时（60s）→ 回到就绪队列 + retry_count++
- retry_count >= 3 → 标记为failed → 通知前端

### Agent中间件管道（middleware.py）

参考DeerFlow的8层中间件链，为Agent基类引入可组合的中间件钩子。
中间件在Agent处理任务的前后执行，处理横切关注点，不污染Agent主逻辑：

```python
class AgentMiddleware(ABC):
    """Agent中间件抽象基类"""
    async def before_task(self, agent, task_context: dict) -> dict:
        """任务处理前调用，可修改context"""
        return task_context

    async def after_task(self, agent, task_context: dict, result: str) -> str:
        """任务处理后调用，可修改result"""
        return result

    async def on_error(self, agent, task_context: dict, error: Exception) -> None:
        """任务出错时调用"""
        pass

# 内置中间件（按需组合）
class LoggingMiddleware(AgentMiddleware):      # 任务开始/结束/耗时日志
class TokenTrackingMiddleware(AgentMiddleware): # 记录LLM token用量
class TimeoutMiddleware(AgentMiddleware):       # 任务超时自动取消
class ContextSummaryMiddleware(AgentMiddleware): # 长上下文自动摘要压缩
class MemoryMiddleware(AgentMiddleware):         # 记忆层读写（Session Memory + Knowledge Graph）
```

中间件执行顺序：`LoggingMiddleware → TokenTrackingMiddleware → TimeoutMiddleware → ContextSummaryMiddleware → MemoryMiddleware → Agent.handle_task()`

> **顺序说明**：ContextSummary 必须在 Memory **之前**——先压缩旧的历史对话上下文腾出窗口空间，再注入新鲜的跨章节记忆上下文。如果顺序反过来，ContextSummary 可能把刚注入的记忆上下文也压缩掉，导致去重精度归零。

BaseAgent 集成：
```python
class BaseAgent:
    middlewares: list[AgentMiddleware] = []

    async def process_task(self, task_context: dict) -> str:
        # 前置中间件链
        ctx = task_context
        for mw in self.middlewares:
            ctx = await mw.before_task(self, ctx)
        # 执行任务
        result = await self.handle_task(ctx)
        # 后置中间件链（逆序）
        for mw in reversed(self.middlewares):
            result = await mw.after_task(self, ctx, result)
        return result
```

### 技能系统（skills/）

参考DeerFlow的Skill progressive loading，为Agent提供可配置的行为模板和写作规范。

**Skill文件格式**（Markdown + YAML frontmatter）：
```markdown
---
name: technical_report
type: writing_style            # writing_style | agent_behavior
applicable_roles: [writer, outline]
applicable_modes: [report]     # report | novel | custom | all
tools: []                      # 该技能需要的MCP工具名称
model_preference: null         # 覆盖默认模型（可选）
description: 技术报告写作规范
---

## 写作指南
- 使用正式学术语气...
```

**两种技能类型**：

| 类型 | 用途 | 注入方式 |
| --- | --- | --- |
| `writing_style` | 写作风格模板（语气、结构、质量标准） | 追加到 Agent system prompt 末尾 |
| `agent_behavior` | Agent 完整行为定义（处理流程、工具使用规则） | 替换 Agent 默认 system prompt |

**技能加载流程**：
```python
class SkillLoader:
    def __init__(self, skills_dir: str = "skills/"):
        self.skills: dict[str, Skill] = {}

    def load_all(self) -> None:
        """扫描 skills/ 目录，解析所有 .md 文件"""

    def match(self, role: str, mode: str) -> list[Skill]:
        """按 Agent角色 + 任务模式 匹配适用技能"""

    def get_prompt_injection(self, role: str, mode: str) -> str:
        """返回拼接后的技能文本，供注入 system prompt"""
```

**Agent集成**（通过中间件）：
```python
class SkillInjectionMiddleware(AgentMiddleware):
    async def before_task(self, agent, ctx: dict) -> dict:
        skills = skill_loader.match(agent.role, ctx.get("mode"))
        ctx["system_prompt"] += "\n\n" + "\n".join(s.content for s in skills)
        # 收集技能声明的MCP工具，追加到agent可用工具列表
        for skill in skills:
            ctx["available_tools"].extend(skill.tools)
        return ctx
```

### MCP客户端集成（mcp/）

Agent 通过 MCP 协议调用外部工具。LLM 通过 function calling 决定何时调用工具。

**配置文件** `mcp_servers.json`：
```json
{
  "servers": {
    "web_search": {
      "command": "uvx",
      "args": ["mcp-server-fetch"],
      "description": "网页抓取工具"
    },
    "brave_search": {
      "command": "npx",
      "args": ["-y", "@anthropic-ai/mcp-server-brave-search"],
      "env": {"BRAVE_API_KEY": "$BRAVE_API_KEY"},
      "description": "Brave搜索引擎"
    }
  }
}
```

**核心组件**：
```python
class MCPClientManager:
    """管理所有MCP服务器连接"""

    async def start(self) -> None:
        """启动时连接所有配置的MCP服务器"""

    async def stop(self) -> None:
        """关闭所有连接"""

    async def list_tools(self) -> list[ToolDefinition]:
        """汇总所有已连接服务器提供的工具"""

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """调用指定工具并返回结果"""

class MCPToolRegistry:
    """将MCP工具转换为OpenAI function calling格式"""

    def to_openai_tools(self, tool_names: list[str]) -> list[dict]:
        """将指定MCP工具转为OpenAI tools schema，供LLM调用"""
```

**Agent调用MCP工具的流程**：
```
1. SkillInjectionMiddleware 注入技能 → 收集技能声明的 tools 列表
2. LLMClient.chat() 发送消息时附带 tools 参数（OpenAI function calling）
3. LLM 返回 tool_call → Agent 通过 MCPClientManager.call_tool() 执行
4. 工具结果追加到消息历史 → 继续对话直到 LLM 返回最终文本
```

**LLMClient 集成**（扩展 chat 接口支持工具调用）：
```python
class LLMClient:
    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        role: str | None = None,
        max_tool_rounds: int = 5,
    ) -> str:
        """
        带工具调用的对话循环：
        1. 发送消息 + tools 给 LLM
        2. 如果 LLM 返回 tool_call → 执行工具 → 追加结果 → 重新发送
        3. 重复直到 LLM 返回纯文本或达到 max_tool_rounds
        """
```

### 上下文管理器（context_manager.py）— 参考OpenClaw三层记忆 + claude-mem渐进式披露

三层记忆架构，为每个Agent角色动态组装最优上下文：

```python
class ContextLayer(Enum):
    WORKING = "working"        # 当前Agent工作状态（Redis Hash，生命周期=单次任务）
    TASK = "task"              # 任务级共享上下文（Redis+PG，生命周期=整个Task）
    PERSISTENT = "persistent"  # 跨任务持久知识（PG+pgvector，生命周期=永久）
```

**Working Memory（Redis Hash）**：
- `agent:{agent_id}:working` — 当前处理的消息、临时变量、最近工具调用结果
- 任务完成后自动清理

**Task Memory（Redis + PostgreSQL）**：
- 大纲全文（outlines表）、术语表（Redis Hash `task:{task_id}:glossary`）
- 已完成章节摘要（Redis Hash `task:{task_id}:chapter_summaries`）
- 审查反馈（chapter_reviews表）、一致性问题清单
- 所有Agent共享读取，只有Manager/Orchestrator写入

**Persistent Memory（PostgreSQL + pgvector）**：
- 历史任务的输出摘要、用户偏好（未来）、写作模板
- 通过pgvector语义检索历史相关内容

核心接口：
```python
class ContextManager:
    async def build_context(
        self, agent_role: str, task_id: str,
        chapter_index: int | None = None
    ) -> list[dict]:
        """
        渐进式披露：按角色组装上下文，避免一次性灌入所有信息
        - Writer: 系统提示 + 大纲摘要 + 本章详情 + 术语表 + 相关审查反馈
        - Reviewer: 系统提示 + 大纲 + 待审章节全文 + 评分标准
        - Consistency: 系统提示 + 大纲 + 各章摘要(非全文) + 检查清单
        """

    async def compress_if_needed(
        self, messages: list[dict], max_ratio: float = 0.75
    ) -> list[dict]:
        """
        上下文压缩：当消息总token超过模型窗口的75%时
        1. 保留系统提示和最近N条消息不变
        2. 用DeepSeek（便宜）摘要中间部分
        3. 返回压缩后的消息列表
        """

    async def summarize_chapter(self, task_id: str, chapter_index: int, content: str) -> str:
        """章节写完后生成摘要，存入Task Memory供其他Agent引用"""
```

**Prompt前缀优化**（利用OpenAI/DeepSeek自动前缀缓存）：
```
组装顺序（静态在前，变量在后，最大化缓存命中）：
[1] 系统提示（per agent role，完全静态）
[2] 技能注入（per task mode，同一任务内静态）
[3] 任务描述 + 大纲（per task，同一任务内静态）
[4] 章节指令 / 审查内容（per agent instance，变量）
[5] 用户追加指令（变量）
```
- OpenAI：≥1024 token前缀自动缓存，命中时输入token打5折
- DeepSeek：≥64 token前缀自动缓存，命中时输入token打9折
- 同一Task的多个Writer共享[1][2][3]前缀 → 高缓存命中率

### RAG检索模块（rag/）— 可选模块，`rag_enabled`配置控制

基于pgvector的轻量级检索增强，用于跨章节一致性检查和未来的参考资料支持：

```python
# chunker.py — 文本分块
class TextChunker:
    def chunk_by_chapter(self, text: str) -> list[Chunk]:
        """按章节标题分割，保留章节元数据"""

    def chunk_by_paragraph(self, text: str, max_tokens: int = 500, overlap: int = 50) -> list[Chunk]:
        """段落级分块，带重叠窗口保持上下文连续性"""

# embedder.py — 嵌入服务
class Embedder:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """通过LLMClient.embed()统一调用text-embedding-3-small"""

    async def embed_and_store(self, task_id: str, chunks: list[Chunk]) -> None:
        """嵌入后写入document_chunks表"""

# retriever.py — 混合检索
class HybridRetriever:
    async def search(
        self, query: str, task_id: str | None = None, top_k: int = 5
    ) -> list[RetrievalResult]:
        """
        混合检索：pgvector余弦相似度 + PostgreSQL tsvector全文搜索
        - 语义搜索：找到概念相近的段落（如不同章节讲述同一主题）
        - 关键词搜索：精确匹配术语、人名、专有名词
        - 结果融合：RRF (Reciprocal Rank Fusion) 合并排序
        """
```

**数据库表**（见数据库Schema节的 `document_chunks` 表定义）

**作为Agent中间件集成**（rag_enabled=false时零开销）：
```python
class RetrievalMiddleware(AgentMiddleware):
    async def before_task(self, agent, ctx: dict) -> dict:
        if not settings.rag_enabled:
            return ctx  # 禁用时直接跳过
        relevant = await self.retriever.search(ctx["task_description"], task_id=ctx["task_id"])
        ctx["retrieved_context"] = relevant
        return ctx
```

### 记忆层（memory/）— cognee 驱动（pip install），`memory_enabled` 配置控制

基于 cognee 的 Graph+Vector 混合知识引擎（`pip install cognee==0.5.5`），通过薄适配层对接项目配置。默认 provider 为 `graph=kuzu`、`vector=lancedb`（cognee 内置默认）。支持的 graph 后端：kuzu / falkor / neo4j_aura_dev；支持的 vector 后端：lancedb / falkor / pgvector。不受支持的组合在 enabled 模式下显式报错。该层解决并行写作内容重复和跨任务知识积累。

**两层记忆架构**：

| 层级 | 存储 | 生命周期 | 用途 |
|------|------|---------|------|
| **Session Memory** | Kuzu 图 + LanceDB 向量（via cognee 0.5.5） | 单次任务 | 并行章节协调、主题领地、内容去重、图片/引用去重 |
| **Knowledge Graph** | 由 cognee promotion lane 管理的 graph/vector 存储 | 永久 | 跨任务知识积累、已验证引用库、实体关系图谱 |

**数据模型**（`memory/models.py`）：
```python
@dataclass
class TopicClaim:
    """章节主题领地声明 — Kuzu 图节点（via cognee）"""
    section_id: str
    topic: str                    # 主题描述
    owns: list[str]               # 本章负责的论点
    boundary: str                 # 本章不覆盖的内容
    confidence: float = 1.0

@dataclass
class ContentSummary:
    """章节内容摘要 — LanceDB 向量 + Kuzu 图节点（via cognee）"""
    section_id: str
    key_points: list[str]         # 核心论点
    word_count: int
    used_image_urls: list[str]
    used_evidence_ids: list[str]
    embedding: list[float] | None = None

@dataclass
class EntityRelation:
    """实体关系 — Knowledge Graph"""
    entity_a: str
    entity_a_type: str            # "concept" | "technology" | "person" | "organization"
    relation: str                 # "relates_to" | "part_of" | "used_by" | "contradicts"
    entity_b: str
    entity_b_type: str
    source_evidence_id: str
    confidence: float = 0.0
```

**SessionMemory 核心接口**（`memory/session.py`）：
```python
class SessionMemory:
    """单次任务记忆 — 统一 API"""

    def __init__(self, session_id: str, config: MemoryConfig):
        self.topic_store = TopicStore(session_id, config)              # Kuzu via cognee
        self.vector_index = VectorIndex(session_id, config)           # LanceDB via cognee
        self.image_registry = ImageRegistry()
        self.embedder = Embedder(config.embedding_model)             # 复用 llm_client.embed()

    async def initialize(self):
        """创建 session 命名空间（Kuzu 图 + LanceDB 向量，via cognee）"""
        # 连接失败时 graceful degradation 到 InMemory 实现

    async def store_territory_map(self, territory: dict[str, TopicClaim]):
        """Outline Agent 完成后：写入章节主题领地分配"""

    async def get_other_sections_context(self, section_id: str) -> dict:
        """Writer/Reviewer 启动前：获取其他章节已写内容"""
        # 返回: other_content(摘要), used_images, territory_map, overlaps

    async def store_content_summary(self, summary: ContentSummary):
        """Writer 完成后：写入本章摘要 + 嵌入向量"""

    async def check_content_overlap(self, content: str, section_id: str, threshold: float = 0.85) -> list[dict]:
        """Reviewer 审查时：检测当前章节与其他章节的语义重叠"""

    async def cleanup(self, knowledge_graph: "KnowledgeGraph" | None = None):
        """任务完成后：可选提升数据到 KG，然后删除 session 命名空间"""
```

**KnowledgeGraph 核心接口**（`memory/knowledge/graph.py`）：
```python
class KnowledgeGraph:
    """跨任务持久知识图谱"""

    async def query_prior_knowledge(self, topic: str, top_k: int = 10) -> list[dict]:
        """新任务启动时：查询历史知识"""

    async def store_entity_relation(self, relation: EntityRelation):
        """存储实体关系（任务完成后 promote）"""

    async def get_cached_references(self, topic: str) -> list[dict]:
        """获取该主题历史已验证引用"""
```

**MemoryMiddleware 集成**（`agents/middleware.py` 新增）：
```python
class MemoryMiddleware(AgentMiddleware):
    """记忆层中间件 — 在 Agent 处理任务前注入记忆上下文，处理后写入摘要"""

    async def before_task(self, agent, ctx: dict) -> dict:
        if not settings.memory_enabled:
            return ctx
        session_memory = get_session_memory(ctx["task_id"])
        if not session_memory:
            return ctx

        # 读取其他章节上下文（仅写作/审查 Agent）
        if agent.role in ("writer", "reviewer", "consistency"):
            memory_ctx = await session_memory.get_other_sections_context(ctx.get("section_id", ""))
            dedup_instruction = build_dedup_instruction(memory_ctx)
            ctx["system_prompt"] += f"\n\n# 跨章节协调\n{dedup_instruction}"

        # Knowledge Graph 查询（仅大纲/写作 Agent）
        if agent.role in ("outline", "writer") and settings.knowledge_graph_enabled:
            kg = KnowledgeGraph(memory_config)
            prior = await kg.query_prior_knowledge(ctx.get("topic", ""))
            if prior:
                ctx["system_prompt"] += f"\n\n# 历史知识参考\n{format_prior_knowledge(prior)}"

        return ctx

    async def after_task(self, agent, ctx: dict, result: str) -> str:
        if not settings.memory_enabled:
            return result
        session_memory = get_session_memory(ctx["task_id"])
        if not session_memory:
            return result

        # Writer 完成后写入章节摘要
        if agent.role == "writer":
            summary = extract_content_summary(ctx, result)
            await session_memory.store_content_summary(summary)

        # Outline Agent 完成后写入主题领地
        if agent.role == "outline":
            territory = extract_territory_map(result)
            await session_memory.store_territory_map(territory)

        return result
```

**四级去重级联流程**：
```
Level 0 — Outline Agent 生成大纲时：
  → 每章输出 topic_claims: {owns: [...], boundary: "..."}
  → 写入 SessionMemory.store_territory_map()

Level 1 — Writer Agent 启动前（MemoryMiddleware.before_task）：
  → 读取 SessionMemory.get_other_sections_context()
  → 注入 prompt: "以下内容已被其他章节覆盖，请勿重复: ..."

Level 2 — Writer Agent 完成后（MemoryMiddleware.after_task）：
  → 写入 SessionMemory.store_content_summary()
  → 后续 Writer 能看到本章摘要

Level 3 — Reviewer Agent 审查时（MemoryMiddleware.before_task）：
  → 调用 SessionMemory.check_content_overlap(current_draft, section_id)
  → 重叠度 > 0.85 → 在 revision_instructions 中要求 Writer 改写重叠段落
```

**Graceful Degradation**：

| 组件不可用 | 降级方案 | 影响 |
|-----------|---------|------|
| Kuzu 连接失败 | `InMemoryTopicStore`（dict 实现） | 丢失图查询，主题领地仍工作 |
| LanceDB 连接失败 | `InMemoryVectorIndex`（numpy 暴力余弦） | 小规模可用，大规模变慢 |
| Embedding API 失败 | 跳过向量相似度，仅关键词去重 | 去重精度下降 |
| `MEMORY_ENABLED=false` | 跳过所有记忆操作，v1 行为 | 无去重 |

**并发安全说明**：

| 组件 | 并发场景 | 安全保证 |
|------|---------|---------|
| Kuzu 写入 | 多个 Writer 同时 store_content_summary | Kuzu ACID 事务，原生并发安全，无需应用层锁 |
| LanceDB upsert | 多个 Writer 同时 upsert 章节嵌入 | LanceDB 原生支持并发 upsert，无需应用层锁 |
| ImageRegistry | 两个 Writer 同时选同一张图片 | **需要 `asyncio.Lock`** — check-then-mark 必须原子化 |
| get_other_sections_context | 读取时其他 Writer 正在写入 | 返回**最终一致性快照**（不是强一致性），后启动的 Writer 天然获得更丰富上下文（Progressive Awareness） |

> **Progressive Awareness 是特性不是缺陷**：并行章节中先完成的章节为后完成的章节提供更丰富的去重上下文。第一个完成的 Writer 看不到其他章节摘要，但最后一个完成的 Writer 能看到所有已完成章节。Level 0 的大纲领地分配为所有 Writer 提供了基线去重能力，不依赖 Progressive Awareness。

**Persistent Memory vs Knowledge Graph 职责分界**：

| 维度 | Persistent Memory (pgvector) | Knowledge Graph (Kuzu/LanceDB via cognee) |
|------|-----|-----|
| **关注** | **怎么写** — 写作偏好、风格规范 | **写什么** — 领域知识、事实性数据 |
| **存什么** | 历史输出摘要、用户偏好（语气/长度/格式）、写作模板 | 实体关系、已验证引用、术语定义 |
| **谁读** | Writer（风格参考）、Outline（结构参考） | Writer（事实参考）、Outline（领域知识）、Reviewer（事实核查） |
| **更新频率** | 低（用户偏好变化慢） | 高（每次任务产出新知识） |
| **查询方式** | 向量语义检索（pgvector cosine） | 图遍历（Kuzu Cypher）+ 向量检索（LanceDB） |
| **管理者** | `context_manager.py` | `memory/knowledge/graph.py` |

### 长文本FSM（long_text_fsm.py）

状态定义：
```python
class LongTextState(Enum):
    INIT = "init"
    OUTLINE = "outline"              # 大纲Agent工作
    OUTLINE_REVIEW = "outline_review" # 用户确认/编辑大纲
    WRITING = "writing"              # 写作Agent并行工作
    REVIEWING = "reviewing"          # 审查Agent逐章评分
    CONSISTENCY = "consistency"       # 一致性Agent全文扫描
    DONE = "done"
    FAILED = "failed"
```

状态转换规则：
```python
class LongTextFSM:
    transitions = {
        "init": ["outline"],
        "outline": ["outline_review"],       # 大纲需要用户确认
        "outline_review": ["writing"],       # 用户确认后进入写作
        "writing": ["reviewing"],
        "reviewing": ["writing", "consistency"],  # 审查不通过回写作（最多3次）
        "consistency": ["writing", "done"],        # 一致性不通过回写作（最多2次）
        "done": [],
    }

    MAX_REVIEW_RETRIES = 3       # 审查不通过最多重写次数
    MAX_CONSISTENCY_RETRIES = 2  # 一致性不通过最多修改次数
    REVIEW_PASS_THRESHOLD = 70   # 审查通过分数阈值

    async def on_enter_writing(self, task):
        """写作阶段：并行生成各章节，每个Writer拿到完整大纲+章节描述+context bridges"""
        outline = task.outline
        chapters = parse_chapters(outline)

        for i, chapter in enumerate(chapters):
            node = create_write_node(
                chapter=chapter,
                full_outline=outline,           # 完整大纲供参考
                context_bridges=chapter.bridges, # 章节间衔接要点
                chapter_index=i
            )
            await scheduler.enqueue(node)  # 并行入队，无依赖关系

    async def on_enter_reviewing(self, task):
        """审查阶段：对每章独立评分（0-100），低于70分退回重写"""
        for chapter in task.chapters:
            review_node = create_review_node(
                chapter=chapter,
                criteria=["accuracy", "coherence", "style", "completeness"]
            )
            await scheduler.enqueue(review_node)

    async def on_enter_consistency(self, task):
        """一致性阶段：全文扫描，生成问题清单发给对应Writer修改"""
        consistency_node = create_consistency_node(
            full_text=task.assembled_text,
            chapters=task.chapters
        )
        await scheduler.enqueue(consistency_node)
```

错误恢复与检查点机制：
```python
class LongTextFSM:
    # ... 上述状态转换 ...

    async def checkpoint(self, task_id: UUID):
        """
        保存FSM检查点到数据库，用于崩溃恢复：
        - 当前FSM状态（fsm_state）
        - 已完成的章节列表及内容
        - 审查/一致性的重试计数
        - 活跃Agent列表
        序列化为JSONB存入 tasks.checkpoint_data
        """

    async def resume(self, task_id: UUID):
        """
        从检查点恢复FSM：
        1. 读取 tasks.checkpoint_data
        2. 恢复FSM到 checkpoint 记录的状态
        3. 跳过已完成的章节，只重新调度未完成的节点
        4. 恢复重试计数器（不因崩溃重置）

        触发时机：服务重启时扫描 status='running' 的任务
        """

    async def _on_state_enter(self, new_state: str, task_id: UUID):
        """每次状态转换后自动保存检查点"""
        await self.checkpoint(task_id)
```

检查点数据结构：
```python
# tasks.checkpoint_data JSONB 示例
{
    "fsm_state": "reviewing",
    "completed_chapters": [0, 1, 3],       # 已完成章节索引
    "review_retry_count": {1: 2, 4: 1},    # 章节索引 → 已重试次数
    "consistency_retry_count": 0,
    "active_nodes": ["uuid-1", "uuid-2"],   # 仍在执行的节点ID
    "checkpoint_at": "2026-03-07T12:00:00Z"
}
```

---

## 数据库Schema（完整DDL）

```sql
CREATE TABLE agents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(100) NOT NULL,
    role        VARCHAR(50) NOT NULL,  -- outline/writer/reviewer/consistency/manager/orchestrator
    layer       SMALLINT NOT NULL,     -- 0编排层 1管理层 2执行层
    capabilities TEXT,
    model       VARCHAR(100) DEFAULT 'gpt-4o',
    status      VARCHAR(20) DEFAULT 'idle', -- idle/busy/offline
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           TEXT NOT NULL,
    mode            VARCHAR(50) NOT NULL,  -- report/novel/custom
    status          VARCHAR(20) DEFAULT 'pending',
    fsm_state       VARCHAR(50) DEFAULT 'init',
    output_text     TEXT,
    word_count      INTEGER DEFAULT 0,
    depth           VARCHAR(20) DEFAULT 'standard', -- quick/standard/deep
    target_words    INTEGER DEFAULT 10000,           -- 目标字数（quick=3000/standard=10000/deep=20000）
    checkpoint_data JSONB,                           -- FSM检查点（崩溃恢复用，含已完成章节/重试计数/活跃节点）
    error_message   TEXT,                            -- 失败原因（status=failed时记录）
    created_at      TIMESTAMP DEFAULT NOW(),
    finished_at     TIMESTAMP
);

CREATE TABLE task_nodes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID REFERENCES tasks(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    agent_role      VARCHAR(50),
    assigned_agent  UUID REFERENCES agents(id),
    status          VARCHAR(20) DEFAULT 'pending',
    depends_on      UUID[],
    result          TEXT,
    retry_count     SMALLINT DEFAULT 0,
    started_at      TIMESTAMP,
    finished_at     TIMESTAMP
);

CREATE TABLE messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id     UUID REFERENCES tasks(id),
    from_agent  VARCHAR(100),
    to_agent    VARCHAR(100),
    msg_type    VARCHAR(50),  -- task_assign/task_result/status_update
    content     JSONB,
    created_at  TIMESTAMP DEFAULT NOW()
);

-- 大纲表（长文本专用）
CREATE TABLE outlines (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id     UUID REFERENCES tasks(id) ON DELETE CASCADE,
    content     TEXT NOT NULL,           -- Markdown格式大纲
    version     SMALLINT DEFAULT 1,      -- 版本号（用户可能编辑多次）
    confirmed   BOOLEAN DEFAULT FALSE,   -- 用户是否确认
    created_at  TIMESTAMP DEFAULT NOW()
);

-- 章节审查记录
CREATE TABLE chapter_reviews (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID REFERENCES tasks(id),
    node_id         UUID REFERENCES task_nodes(id),
    chapter_index   SMALLINT,
    score           SMALLINT,            -- 0-100
    accuracy_score  SMALLINT,
    coherence_score SMALLINT,
    style_score     SMALLINT,
    feedback        TEXT,
    pass            BOOLEAN,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- Agent心跳记录（用于监控，历史数据定期清理）
CREATE TABLE agent_heartbeats (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id    UUID REFERENCES agents(id),
    task_id     UUID,
    status      VARCHAR(20),
    created_at  TIMESTAMP DEFAULT NOW()
);
```

```sql
-- 文档分块表（RAG检索，pgvector扩展）
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE document_chunks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID REFERENCES tasks(id) ON DELETE CASCADE,
    source_type     VARCHAR(50),        -- 'chapter' | 'outline' | 'reference'
    chapter_index   SMALLINT,
    content         TEXT NOT NULL,
    embedding       vector(1536),       -- text-embedding-3-small
    tsv             tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
    metadata        JSONB,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_chunks_embedding ON document_chunks
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX idx_chunks_tsv ON document_chunks USING gin(tsv);
CREATE INDEX idx_chunks_task ON document_chunks(task_id);
```

---

## 结构化日志规范（logger.py）

所有日志必须携带结构化上下文字段，便于多Agent并发时的日志关联和问题排查：

```python
from loguru import logger

# 全局配置（在 main.py 启动时设置）
logger.configure(
    handlers=[
        {"sink": "logs/hierarch.log", "format": "{time} | {level} | {extra} | {message}", "rotation": "50 MB"},
        {"sink": sys.stderr, "format": "{time:HH:mm:ss} | {level} | {message}", "level": "INFO"},
    ]
)

# Agent内部使用 bind() 绑定上下文
class BaseAgent:
    def __init__(self, agent_id, task_id):
        self.log = logger.bind(
            agent_id=str(agent_id),
            task_id=str(task_id),
            role=self.role,
        )

    async def run(self):
        self.log.info("Agent started")           # → {"agent_id": "xxx", "task_id": "yyy", "role": "writer"}
        self.log.info("Chapter written", chapter_index=2, word_count=1500)
```

日志字段规范：

| 字段 | 类型 | 何时绑定 | 用途 |
|------|------|----------|------|
| `task_id` | UUID | Agent创建时 | 关联同一任务的所有日志 |
| `agent_id` | UUID | Agent创建时 | 区分同角色的不同Agent实例 |
| `role` | str | Agent创建时 | 按角色过滤（writer/reviewer等） |
| `node_id` | UUID | 处理具体节点时 | 关联到DAG节点 |
| `chapter_index` | int | 写作/审查时 | 定位到具体章节 |
| `model` | str | LLM调用时 | 追踪模型使用情况 |
| `tokens_in/out` | int | LLM调用后 | Token成本追踪 |
| `duration_ms` | int | 操作完成时 | 性能追踪 |

日志级别约定：
- **DEBUG**：LLM prompt/response原文（仅debug模式）
- **INFO**：状态转换、Agent启停、章节完成
- **WARNING**：重试、降级、超时接近
- **ERROR**：LLM调用失败、数据库异常、FSM非法转换

---

## 测试策略（LLM Mock）

LLM调用是外部依赖，测试时必须隔离。采用依赖注入 + Mock客户端模式：

```python
# utils/llm_client.py — 抽象基类
from abc import ABC, abstractmethod

class BaseLLMClient(ABC):
    @abstractmethod
    async def chat(self, messages, model=None, role=None, **kwargs) -> str: ...

    @abstractmethod
    async def chat_json(self, messages, model=None, role=None, schema=None) -> dict: ...

    @abstractmethod
    async def embed(self, texts: list[str], model=None) -> list[list[float]]: ...

class LLMClient(BaseLLMClient):
    """真实实现：调用OpenAI/DeepSeek API"""
    ...

# tests/conftest.py — Mock实现
class MockLLMClient(BaseLLMClient):
    """测试用Mock：返回预设响应，不调用任何外部API"""

    def __init__(self):
        self.call_log: list[dict] = []  # 记录所有调用，供断言

    async def chat(self, messages, model=None, role=None, **kwargs) -> str:
        self.call_log.append({"method": "chat", "messages": messages, "role": role})
        # 按角色返回预设响应
        if role == "outline":
            return MOCK_OUTLINE_RESPONSE
        if role == "writer":
            return MOCK_CHAPTER_RESPONSE
        if role == "reviewer":
            return MOCK_REVIEW_RESPONSE
        return "mock response"

    async def chat_json(self, messages, model=None, role=None, schema=None) -> dict:
        self.call_log.append({"method": "chat_json", "role": role})
        if role == "orchestrator":
            return MOCK_DAG_JSON
        return {"result": "mock"}

    async def embed(self, texts: list[str], model=None) -> list[list[float]]:
        self.call_log.append({"method": "embed", "count": len(texts)})
        return [[0.1] * 1536 for _ in texts]  # 固定维度的假向量

# tests/conftest.py — pytest fixture
@pytest.fixture
def mock_llm():
    return MockLLMClient()

@pytest.fixture
def llm_client(mock_llm):
    """所有测试默认使用Mock，集成测试可覆盖此fixture"""
    return mock_llm
```

测试分层：
| 层级 | 范围 | LLM | 数据库 | 运行频率 |
|------|------|-----|--------|----------|
| 单元测试 | 单个函数/类 | MockLLMClient | SQLite内存 | 每次提交 |
| 集成测试 | 服务间协作 | MockLLMClient | PostgreSQL测试库 | PR合并前 |
| 端到端测试 | 完整流程 | 真实API（有速率限制） | PostgreSQL测试库 | 手动触发 |

关键测试fixture：
```python
# tests/conftest.py
@pytest.fixture
async def db_session():
    """每个测试独立的数据库session，测试后自动回滚"""
    async with async_session() as session:
        async with session.begin():
            yield session
            await session.rollback()

@pytest.fixture
def mock_redis():
    """fakeredis替代真实Redis（pip install fakeredis[lua]已在requirements.txt）"""
    import fakeredis.aioredis
    return fakeredis.aioredis.FakeRedis()
```

---

## 环境变量（.env.example）

```env
# 数据库
POSTGRES_URL=postgresql+asyncpg://user:password@localhost:5432/agent_db

# Redis
REDIS_URL=redis://localhost:6379/0

# LLM
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEFAULT_MODEL=gpt-4o
MAX_CONCURRENT_LLM_CALLS=5

# RAG（可选）
RAG_ENABLED=false
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536

# Memory Layer（记忆层，自研）
MEMORY_ENABLED=true
# Memory (cognee defaults: kuzu + lancedb, no extra config needed)
MEMORY_ENABLED=false
GRAPH_DATABASE_PROVIDER=kuzu
VECTOR_DATABASE_PROVIDER=lancedb
MEMORY_OVERLAP_THRESHOLD=0.85
KNOWLEDGE_GRAPH_ENABLED=true
KG_PROMOTE_MIN_CREDIBILITY=0.7

# 应用
APP_HOST=0.0.0.0
APP_PORT=8000
DEBUG=true
```

## 参考仓库落地设计补丁（2026-03-21）

### 1. FSM 扩展建议
1. 状态扩展：`PRE_REVIEW_INTEGRITY`、`RE_REVIEW`、`RE_REVISE`、`FINAL_INTEGRITY`。
2. 转移规则：
   - `WRITING -> PRE_REVIEW_INTEGRITY -> REVIEWING`
   - `REVIEWING -> RE_REVIEW/RE_REVISE`（按评分与决策）
   - `RE_REVIEW/RE_REVISE -> FINAL_INTEGRITY -> DONE`

### 2. 审查与完整性数据结构（建议）
1. `chapter_reviews` 增加字段：`rubric_json`、`devils_advocate`。
2. 新增 `integrity_reports` 表：
   - `phase`（pre_review/final）
   - `claim_checks`（jsonb）
   - `summary_score`
   - `blocking_issues`

### 3. Prompt 与技能注入链路
1. Prompt Loader 增加“阶段模板叠加”能力。
2. Skill Loader 增加“阶段 profile 匹配”能力。
3. Middleware 注入顺序建议：
   - ContextSummary -> Memory -> StageSkillInjection -> AgentExecution。

### 4. 调度策略
1. 完整性节点默认高优先级且串行执行。
2. 复审节点可并行（按章节），但汇总决策节点必须串行。
3. 在 assignment payload 中增加 `checkpoint_type` 与 `entry_stage_detected` 供 Agent 决策与审计。

## 2026-03-21 Backend Addendum — Step 4.2 Deep Integration
Code path (retry/fallback overrides):
- `services/dag_scheduler.py` -> assignment payload
- `agents/runtime_config.py` -> `resolve_llm_call_params(ctx)`
- `agents/{worker,manager,orchestrator}.py` -> forward overrides
- `services/task_decomposer.py` -> `chat_json(..., max_retries, fallback_models)`
- `utils/llm_client.py` -> `_call_with_retry(...)` + `_resolve_fallback_chain(...)`

Test coverage focus:
- propagation from payload to LLM callsites
- fallback-chain override and dedup behavior
- default behavior when overrides absent
