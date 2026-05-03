# 5维度全景诊断 — Pipeline & 结构优化方案

**诊断对象**：thinkweave 长文本生成系统  
**诊断日期**：2026-05-03  
**关注维度**：执行流程 / 数据流 / Agent协作 / 状态管理 / 实时反馈

---

## 1️⃣ 执行流程诊断

### 现状

```
用户创建任务
    ↓
Orchestrator Agent 分解任务 → DAG（10-20个节点）
    ↓
DAG Scheduler 定时轮询（1s/次）
    ├─ 检查已完成节点 → 从 Redis Stream 读取结果
    ├─ 检查超时节点 → 从 Sorted Set 读取
    ├─ 计算就绪节点 → 检查前置依赖
    ├─ 匹配空闲Agent → 受并发上限约束
    ├─ 分配任务 → XADD 到 agent:{id}:inbox
    └─ 失败重试 → 最多3次
    ↓
Writer/Reviewer/Consistency Agent 执行具体任务
    ↓
FSM 驱动状态转移 → 14个状态
    ├─ INIT → OUTLINE → OUTLINE_REVIEW → WRITING → ...
    └─ MAX_REVIEW_RETRIES=3, MAX_CONSISTENCY_RETRIES=2
    ↓
最终生成文本 → 导出 DOCX/PDF
```

### 发现的问题

| # | 问题 | 影响 | 严重度 |
|---|------|------|--------|
| 1 | **DAG调度是轮询**，不是事件驱动 | 需要节点完成→等待下一秒轮询才能分配新任务；30k字文本可能多等 50-100ms | 中 |
| 2 | **FSM 和 DAG Scheduler 交叉通信** | FSM 维护全局状态机，DAG 维护节点调度；超过一定规模易产生竞态条件 | 中-高 |
| 3 | **重试逻辑分散** | DAG里有MAX_RETRIES=3，FSM里有MAX_REVIEW_RETRIES=3、MAX_CONSISTENCY_RETRIES=2；不清楚哪层重试失败就终止 | 高 |
| 4 | **Checkpoint粗粒度** | 检查点只保存"已完成章节"，不保存中间 context/去重信息；恢复时丢失记忆 | 高 |
| 5 | **大纲审查 OUTLINE_REVIEW** | 是等待用户手动确认的阻塞点，但没有超时/重定向机制；30k字任务若卡在这，后续所有并发就没用 | 中-高 |
| 6 | **PRE_REVIEW_INTEGRITY 和 FINAL_INTEGRITY** | 这两个 integrity check 节点的职责不清（与 consistency 的关系是什么？）；容易重复或遗漏 | 中 |

### 根因分析

1. **流程设计源头**：没有把执行流程和状态管理分离；FSM 包含太多业务逻辑，而不只是状态转移
2. **调度机制**：选择轮询而非事件驱动，导致延迟可累加
3. **错误恢复**：多层重试没有统一的 backoff/circuit-breaker 策略

### 优化方案

#### 方案 A：分离 Flow Controller 和 State Machine

```
现在（混合）：
FSM (long_text_fsm.py)
  ├─ 状态转移逻辑
  ├─ DAG 管理
  ├─ Agent 分配
  └─ 重试控制
    
改进（分离）：
┌─ FlowController (新建)
│   ├─ 协调 FSM 和 DAG Scheduler
│   ├─ 驱动状态转移
│   ├─ 错误路由
│   └─ 超时处理
├─ LongTextFSM (简化)
│   ├─ 只维护状态 + 转移规则
│   └─ 无业务逻辑耦合
└─ DAGScheduler (现有)
    ├─ 节点调度
    ├─ 并发控制
    └─ 本层重试
```

#### 方案 B：事件驱动替代轮询

```
现在：
每 1s 轮询一次 → 检查所有节点状态 → O(n) 次数据库查询

改进：
节点完成时 XADD 事件 → Scheduler 直接消费 → 立即计算就绪节点 → O(1) 响应
```

#### 方案 C：统一重试策略

```
DAG 层：
  - 执行失败 → 重试（max 3次，指数退避：1s→2s→4s）
  - 3次后检查是否是瞬时错误 → 否则转 circuit-breaker

FSM 层：
  - 审查/一致性检查失败 → 交给对应 Agent 重新执行（max 2-3次）
  - 检查是否是 Agent 能力问题 → 否则标记节点 dead-letter

统一：
  - 所有重试共用一个 Backoff Calculator
  - 所有 circuit-breaker 共用一个 Registry
```

#### 方案 D：充实 Checkpoint 内容

```
现在：
{
  "completed_chapters": ["ch1", "ch2"],
  "retry_count": 3
}

改进：
{
  "completed_chapters": ["ch1", "ch2"],
  "retry_count": {"ch3": 1, "ch4": 2},  # 按章节
  "session_memory_snapshot": {...},      # 去重信息
  "topic_territory_map": {...},          # 章节领地
  "last_checkpoint_time": "2026-05-03T12:00:00Z",
  "dedup_registry_hash": "sha256:xxx",   # 校验完整性
  "agent_context_cache": {...}           # 上下文快照
}
```

#### 方案 E：大纲审查的超时和降级

```
OUTLINE_REVIEW 状态：
  - 设置 30 分钟超时（可配置）
  - 如果超时未确认：
    a) 发送提醒通知
    b) 允许"自动通过"（需明确权限）
    c) 生成"备用大纲"供后续使用
  - 不阻塞其他流程的初始化工作
```

---

## 2️⃣ 数据流诊断

### 现状

```
任务创建
  ↓ task.py + task_node.py
数据库 (PostgreSQL)
  ├─ 读：DAG Scheduler 定时查询所有节点状态
  ├─ 写：Agent 完成后更新 task_node.output
  └─ 读写竞态：无 DB-level 乐观锁

Agent 执行
  ↓ Redis Streams
Redis 通信 (消息总线)
  ├─ agent:{id}:inbox — Agent 接收任务
  ├─ task:{id}:events — WebSocket 推送
  └─ system:logs — 日志汇总

Memory/RAG
  ↓ 三层系统
SessionMemory (当前任务)
  ├─ 去重：set(已生成的内容 hash)
  ├─ 领地：map(章节 → owned_topics)
  └─ 使用引擎：cognee adapter (pip install)

KnowledgeGraph (跨任务)
  ├─ 实体关系
  └─ 使用引擎：cognee adapter

RAG (检索)
  ├─ pgvector (PostgreSQL 嵌入)
  ├─ tsvector (全文搜索)
  └─ RRF 融合排序

LLM 调用
  ↓ llm_client.py
统一接口
  ├─ OpenAI / DeepSeek 双端点
  ├─ 流式 / JSON / 工具调用
  ├─ 自动降级（主模型失败 → fallback）
  └─ Token 追踪
```

### 发现的问题

| # | 问题 | 影响 | 严重度 |
|---|------|------|--------|
| 1 | **DB 查询没有乐观锁** | 并发 Agent 可能同时读-写同一节点；导致结果覆盖 | 高 |
| 2 | **Memory / RAG / Utils 有重复** | embedding.py, context_manager.py, session.py 都在处理向量/上下文；代码重复 | 中 |
| 3 | **Cognee adapter 依赖重** | pip install cognee 拉 35+ 依赖；如果 cognee 出问题难以降级 | 中 |
| 4 | **SessionMemory 在内存中** | 如果 Agent 进程重启，内存中的去重数据全丢 | 高 |
| 5 | **LLM 调用的 token 追踪不准** | token_tracker.py 是事后聚合，不是实时；bill 时会有延迟和偏差 | 低-中 |
| 6 | **上下文压缩触发不明确** | context_manager 说"超过 75% 就压缩"，但没有具体的触发阈值监控 | 中 |
| 7 | **RAG 检索的输入验证缺失** | retriever.py 没有对查询文本长度/质量的校验；可能返回空或大量噪声 | 中 |

### 根因分析

1. **缺乏原子性保障**：DB 操作和 Redis 消息不同步
2. **依赖过重**：用了太多库（cognee、pgvector、lancedb）；单点故障风险高
3. **内存持久化不足**：关键数据（SessionMemory）没有持久化选项

### 优化方案

#### 方案 A：引入 DB 乐观锁

```python
# 在 TaskNode ORM 中添加
class TaskNode:
    version = Column(Integer, default=0)  # 版本号
    
# 更新时
stmt = (
    update(TaskNode)
    .where((TaskNode.id == node_id) & (TaskNode.version == expected_version))
    .values(output=new_output, version=TaskNode.version + 1)
)
result = await session.execute(stmt)
if result.rowcount == 0:
    raise ConcurrentModificationError("Node was modified by another agent")
```

#### 方案 B：分离 Memory/RAG/Utils 职责边界

```
新建 core/
├─ embedding.py (唯一嵌入入口，无重复)
├─ context.py (统一上下文组装，不与 memory 混淆)
├─ prompt.py (Prompt 加载 + 渲染)
└─ llm.py (LLM 调用 + 重试 + Token 追踪)

memory/
├─ session.py (当前任务去重/领地)
└─ knowledge/ (跨任务图谱)
  
rag/
├─ retriever.py (输入验证 + 检索)
└─ (依赖 core/embedding.py)
```

#### 方案 C：SessionMemory 持久化

```
现在：内存字典 + cognee

改进：
SessionMemory
  ├─ 缓存层：内存（快）
  ├─ 持久层：Redis Hash (session:{task_id}:dedup) / (session:{task_id}:territory)
  └─ 降级：若 Redis 不可用，只用内存（有风险但能运行）

恢复时：
  task 重启 → 检查 Redis 中是否有 session:{task_id}:* → 读取恢复
```

#### 方案 D：Cognee 依赖隔离

```
现在：
from cognee import add, search, cognify  # 直接依赖

改进（adapter 模式）：
memory/
├─ adapter.py (cognee 适配层)
│   └─ def add(data): 
│       try: return cognee.add(data)
│       except: return fallback_inmemory_add(data)
└─ __init__.py
    def get_memory_backend():
        if settings.MEMORY_BACKEND == 'cognee':
            return CogneeMemory()
        elif settings.MEMORY_BACKEND == 'inmemory':
            return InMemoryMemory()
        else:
            raise ConfigError(...)

这样 Cognee 故障 → 自动降级到内存；不影响系统可用性
```

#### 方案 E：RAG 检索输入验证

```python
def validate_query(query: str) -> bool:
    if not query or len(query.strip()) == 0:
        return False
    if len(query) > 2000:  # 过长
        return False
    if query.count(' ') < 2:  # 太短/单词太少
        return False
    return True

def search_with_fallback(query: str, top_k: int = 5):
    if not validate_query(query):
        logger.warn(f"Invalid query: {query}")
        return []  # 返回空而不是噪声
    try:
        results = pgvector_search(query, top_k=top_k)
        if len(results) == 0:
            logger.debug(f"No semantic results for: {query}, trying full-text")
            results = fulltext_search(query, top_k=top_k)
        return results
    except Exception as e:
        logger.error(f"Retrieval failed: {e}")
        return []
```

---

## 3️⃣ Agent 协作诊断

### 现状

```
三层 Agent 架构：

Layer 0：Orchestrator
  └─ 输入：用户任务描述 + 风格 + 长度
  └─ 输出：DAG（节点 + 依赖关系）
  └─ 1个固定实例

Layer 1：Manager
  └─ 监听：FSM 状态转移事件
  └─ 职责：协调 Writer/Reviewer/Consistency 的执行
  └─ 1个固定实例（虽然架构上讲"可多个"）

Layer 2：Workers
  ├─ Writer Agent (并行 N 个实例)
  │   ├─ 消费：WRITING 状态下的 DAG 节点
  │   ├─ 输出：Markdown 章节文本
  │   └─ 启动前：从 SessionMemory 读取去重数据
  │
  ├─ Reviewer Agent (1-N 个，按并发调整)
  │   ├─ 消费：REVIEWING 状态下的章节评分任务
  │   ├─ 输出：0-100 分数 + 反馈
  │   └─ 触发：review_score ≥ 70 通过，否则 re_write
  │
  └─ Consistency Agent (1 个)
      ├─ 消费：CONSISTENCY 状态
      ├─ 输入：SessionMemory 中的章节摘要（不读全文）
      └─ 输出：不一致问题列表 → 路由回对应 Writer 修复
```

### 发现的问题

| # | 问题 | 影响 | 严重度 |
|---|------|------|--------|
| 1 | **Manager 没有明确的职责清单** | "协调"很模糊；实际是在 FSM 和 DAG 之间传递信号，易成为瓶颈 | 中-高 |
| 2 | **Writer 并行度无上限** | 理论上可以 N 个 Writer；但没有对 LLM token/req 的真实限流 | 高 |
| 3 | **Reviewer 和 Consistency 的关系不清** | 都在做"质量检查"；Reviewer 评分，Consistency 检查重叠——是互补还是重复？ | 中 |
| 4 | **Agent 启动没有健康检查** | 无法判断某个 Agent 启动失败；系统会一直等待 | 中 |
| 5 | **上下文在 Agent 间流转无协议** | 每个 Agent 手动从 DB/Redis 读上下文；容易缺数据或读脏数据 | 高 |
| 6 | **Fallback 机制缺失** | 某个 Writer 失败 N 次后，没有"降级到简化版"的逻辑 | 中 |
| 7 | **Agent 之间无优先级** | 所有章节并行 → 但某些章节可能需要依赖其他章节信息 | 中 |

### 根因分析

1. **职责定义过于抽象**：Layer 1/2 的边界模糊
2. **资源管理不精细**：Writer 数量和 Token 限制没有绑定
3. **通信协议简陋**：Agent 间靠"读 DB"通信，没有明确的上下文传递格式

### 优化方案

#### 方案 A：明确 Manager 职责 + 事件驱动协调

```
改进前：Manager 是"中转站"

改进后：Manager 是"Orchestration FSM 驱动"
  
Manager 职责：
  1. 监听 FSM 状态事件 (state_changed)
  2. 根据当前状态 → 发起 Agent 集群操作
     a) 状态 WRITING → 启动 N 个 Writer (并发受限)
     b) 状态 REVIEWING → 启动 Reviewer 批处理
     c) 状态 CONSISTENCY → 启动单个 Consistency 扫描
  3. 收集 Agent 结果 → 驱动状态转移
  4. 错误时：触发重试或降级
  
代码结构：
class ManagerAgent(BaseAgent):
    state_event_stream = "task:{task_id}:state_events"
    
    async def handle_state_event(self, event):
        if event.from_state == "outline_review" and event.to_state == "writing":
            await self.spawn_writers(count=min(len(dag.chapters), MAX_WRITERS))
            await self.spawn_reviewers(count=MAX_REVIEWERS)
        elif event.from_state == "reviewing" and event.to_state == "consistency":
            await self.spawn_consistency_check()
```

#### 方案 B：Writer 并发限流（按 Token + 请求数）

```
现在：无限制

改进：
class WriterPool:
    def __init__(self):
        self.active_writers = 0
        self.token_budget_per_window = settings.MAX_TOKENS_PER_MINUTE
        self.token_used_this_window = 0
    
    async def acquire_write_slot(self, estimated_tokens: int):
        # 等待直到有可用槽位
        while self.active_writers >= settings.MAX_CONCURRENT_WRITERS:
            await asyncio.sleep(0.1)
        
        # 等待直到 token 预算够
        while self.token_used_this_window + estimated_tokens > self.token_budget_per_window:
            await asyncio.sleep(1)
        
        self.active_writers += 1
        self.token_used_this_window += estimated_tokens
        
    async def release_write_slot(self, actual_tokens_used: int):
        self.active_writers -= 1
        # 每 60s 重置 token 预算
```

#### 方案 C：Reviewer / Consistency 的分工明确

```
Reviewer Agent：
  职责：评估单个章节的"质量"（0-100分）
  检查点：
    - 是否符合指定字数
    - 是否按指令完成
    - 写作风格是否一致
    - 语法/逻辑错误
  输出：score + feedback + suggestions_for_rewrite
  决策：score >= 70 → pass; < 70 → trigger re_write

Consistency Agent：
  职责：全局一致性检查（章节间）
  检查点：
    - 术语一致性（是否同一概念多种表述）
    - 逻辑连贯性（前后矛盾）
    - 引用完整性（是否缺少定义）
    - 重复内容检测（Reviewer 已检查单章，Consistency 检查跨章重复）
  输出：issue_list = [{"chapter_id": "ch2", "problem": "与ch1矛盾", "suggestion": "修改..."}]
  决策：问题数 > threshold → trigger re_write for affected chapters

关键区分：
  Reviewer = 质量检查（单章内）
  Consistency = 连贯检查（全书范围）
```

#### 方案 D：Agent 健康检查 + 启动验证

```python
class AgentHealthCheck:
    async def check_agent_startup(self, agent_id: uuid.UUID, timeout: int = 30):
        """检查 Agent 是否成功启动"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            state = await get_agent_state(agent_id)  # Redis Hash
            if state and state.get('status') == 'running':
                return True
            await asyncio.sleep(1)
        
        logger.error(f"Agent {agent_id} failed to start within {timeout}s")
        raise AgentStartupTimeoutError(agent_id)

# 使用
await spawn_writers(count=5)
for writer_id in writer_ids:
    await check_agent_startup(writer_id)  # 会抛异常
```

#### 方案 E：上下文流转协议

```
定义显式的"context envelope"：

class AgentContextEnvelope:
    task_id: UUID
    node_id: UUID
    source_agent: str
    target_agent: str
    context_type: Literal["outline", "chapter_context", "memory_snapshot", "feedback"]
    payload: dict  # 具体内容
    timestamp: datetime
    version: int  # schema 版本
    
# Agent 间通信
async def pass_context(envelope: AgentContextEnvelope):
    # 序列化 → XADD 到 agent:{target}:context
    key = f"agent:{envelope.target_agent}:context"
    await redis.xadd(key, {
        "envelope": envelope.json(),
        "source": envelope.source_agent,
        "created_at": envelope.timestamp.isoformat(),
    })

# Agent 接收
async def receive_context(agent_id: str) -> AgentContextEnvelope:
    key = f"agent:{agent_id}:context"
    messages = await redis.xread(key, count=1)
    if messages:
        data = messages[0][1][0][1]
        return AgentContextEnvelope.parse_raw(data['envelope'])
```

---

## 4️⃣ 状态管理诊断

### 现状

```
状态维度：

Task 级（tasks 表）
  ├─ status: created | decomposed | generating | reviewing | done | failed
  ├─ fsm_state: FSM 14 个状态之一
  ├─ checkpoint_data: JSONB (completed_chapters, retry_count)
  └─ output_text, word_count

Node 级（task_node 表）
  ├─ status: pending | ready | running | done | failed | skipped
  ├─ output: 执行结果文本
  ├─ retry_count: 当前重试次数
  └─ started_at, completed_at

Agent 级（Redis Hash）
  ├─ agent:{id}:state
  │   ├─ status: idle | busy
  │   ├─ current_task: 当前在执行的 task_id
  │   ├─ last_heartbeat: 时间戳
  │   └─ error_count: 累计错误数
  └─ 超时检测：若 last_heartbeat 超过 30s 无更新 → 标记为 dead

FSM 状态机
  └─ 14 个状态 + 手工转移规则（TRANSITIONS dict）
```

### 发现的问题

| # | 问题 | 影响 | 严重度 |
|---|------|------|--------|
| 1 | **多层状态不同步** | task.status / task.fsm_state / task_node.status 三者有时不一致；容易陷入"僵尸"状态 | 高 |
| 2 | **状态转移没有事件通知** | FSM 转移时只更新 DB，不发送事件；下游 Agent/WebSocket 通过轮询感知，延迟 1s | 中 |
| 3 | **Checkpoint 恢复不完整** | 只记录"已完成章节"，不记录"当前 FSM 路径"；恢复时可能走错分支 | 中-高 |
| 4 | **Agent 心跳和状态脱离** | Agent 发心跳和更新任务状态是两套流程；可能心跳通畅但任务结果丢失 | 中 |
| 5 | **没有状态转移日志** | 无法审计"为什么从 WRITING 跳到 FAILED"；排查问题困难 | 中 |
| 6 | **Node 级 retry_count 和 FSM MAX_RETRIES 冗余** | DAG 层也在算重试，FSM 层也在算；易重复或遗漏 | 中 |
| 7 | **无法手动干预状态** | 一旦卡住，必须 kill/restart；无法"强制转移"或"跳过某节点" | 中 |

### 根因分析

1. **状态层级没有统一视图**：DB 中 3 套状态，Redis 中 1 套，各自为政
2. **事件驱动不足**：事件到达后等待轮询才能反应
3. **可观测性弱**：无状态转移日志，无便于排查的工具

### 优化方案

#### 方案 A：统一状态视图 + 事件源

```
新建 StateStore 抽象层：

class StateStore:
    """状态的单一真实来源"""
    
    async def get_task_state(self, task_id: UUID) -> TaskState:
        """返回完整视图，包括 FSM + Nodes + Agents"""
        return {
            "task_id": task_id,
            "fsm_state": await self._get_fsm_state(task_id),
            "nodes_state": await self._get_nodes_state(task_id),
            "agent_state": await self._get_agent_state(task_id),
            "last_update": now(),
        }
    
    async def transition_fsm(
        self, 
        task_id: UUID, 
        from_state: str, 
        to_state: str,
        reason: str,
        metadata: dict = None
    ) -> bool:
        """原子地转移状态 + 发送事件"""
        # 在事务中完成
        async with async_session_factory() as session:
            async with session.begin():
                # 1. 检查当前状态
                task = await session.get(Task, task_id)
                if task.fsm_state != from_state:
                    raise InvalidTransitionError(task.fsm_state, to_state)
                
                # 2. 验证转移合法性
                if not self._is_valid_transition(from_state, to_state):
                    raise InvalidTransitionError(from_state, to_state)
                
                # 3. 更新状态
                task.fsm_state = to_state
                task.updated_at = now()
                
                # 4. 记录转移日志
                await session.add(StateTransitionLog(
                    task_id=task_id,
                    from_state=from_state,
                    to_state=to_state,
                    reason=reason,
                    metadata=metadata,
                    created_by="system",
                ))
                
                # 5. 发送事件
                await redis.xadd(f"task:{task_id}:state_events", {
                    "type": "state_transition",
                    "from_state": from_state,
                    "to_state": to_state,
                    "reason": reason,
                    "timestamp": now().isoformat(),
                })
        
        return True
```

#### 方案 B：事件驱动替代轮询

```
现在：
WebSocket ← 轮询 task.fsm_state (每 1-2s)

改进：
task:{task_id}:state_events (Redis Stream)
  ← FSM 转移时 XADD
  ← WebSocket handler 监听 XREAD
  ← 实时推送到前端
  
代码示例：
async def ws_listen_for_state_updates(task_id: UUID):
    last_id = "0"
    while True:
        messages = await redis.xread(f"task:{task_id}:state_events", last_id, count=10)
        for msg_id, msg_data in messages:
            # 实时推送给前端
            await ws.send_json({
                "type": "state_update",
                "data": msg_data,
            })
            last_id = msg_id
        await asyncio.sleep(0.1)  # 短暂等待避免 CPU 空转
```

#### 方案 C：完整的 Checkpoint 结构

```python
class CheckpointData:
    """可完整恢复的检查点"""
    
    # 核心状态
    fsm_state: str
    fsm_path: list[str]  # 从 INIT 到当前状态的转移路径
    
    # 节点状态
    completed_nodes: list[UUID]
    pending_nodes: list[UUID]
    failed_nodes: dict[UUID, str]  # node_id -> error_message
    
    # 重试计数（按节点）
    retry_count: dict[UUID, int]
    
    # 记忆恢复
    session_memory_snapshot: dict  # 去重数据
    topic_territory_map: dict  # 章节领地
    dedup_registry_hash: str  # 校验
    
    # Agent 上下文
    agent_context_cache: dict[str, dict]  # agent_id -> context
    
    # 时间戳
    created_at: datetime
    last_updated_at: datetime

# 恢复逻辑
async def resume_from_checkpoint(task_id: UUID):
    cp = await load_checkpoint(task_id)
    
    # 1. 恢复 FSM 状态
    current_task.fsm_state = cp.fsm_state
    
    # 2. 恢复 Node 状态
    for node_id in cp.completed_nodes:
        update_node_status(node_id, "done")
    for node_id in cp.pending_nodes:
        update_node_status(node_id, "pending")
    
    # 3. 恢复 SessionMemory
    await session_memory.restore_from_snapshot(cp.session_memory_snapshot)
    
    # 4. 恢复 Agent 上下文
    for agent_id, ctx in cp.agent_context_cache.items():
        await cache_agent_context(agent_id, ctx)
    
    # 5. 继续执行（从当前节点开始）
    await dag_scheduler.resume()
```

#### 方案 D：状态转移日志 + 审计

```sql
-- 新建表
CREATE TABLE state_transition_logs (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES tasks(id),
    from_state VARCHAR(50) NOT NULL,
    to_state VARCHAR(50) NOT NULL,
    reason VARCHAR(500),
    metadata JSONB,  -- 额外信息，如错误堆栈
    created_by VARCHAR(100),  -- "system" / "user" / "agent:id"
    created_at TIMESTAMP NOT NULL,
    
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE INDEX idx_state_transition_task ON state_transition_logs(task_id, created_at DESC);
```

#### 方案 E：手动干预接口

```python
# 新增 API 端点

@router.post("/api/tasks/{task_id}/force-transition")
async def force_state_transition(
    task_id: UUID, 
    target_state: str,
    reason: str,
    current_user: User = Depends(get_current_user)
):
    """仅允许 admin 强制转移状态"""
    
    if not current_user.is_admin:
        raise PermissionDenied()
    
    task = await get_task(task_id)
    old_state = task.fsm_state
    
    # 记录强制转移
    await state_store.transition_fsm(
        task_id, 
        old_state, 
        target_state,
        reason=f"Forced by {current_user.email}: {reason}",
        metadata={"forced": True, "user_id": current_user.id}
    )
    
    logger.warning(f"Task {task_id} forcefully transitioned from {old_state} to {target_state}")
    
    return {"success": True, "old_state": old_state, "new_state": target_state}

@router.post("/api/tasks/{task_id}/skip-node")
async def skip_node(
    task_id: UUID,
    node_id: UUID,
    reason: str,
    current_user: User = Depends(get_current_user)
):
    """跳过某个失败的节点，继续执行"""
    
    if not current_user.is_admin:
        raise PermissionDenied()
    
    node = await get_node(node_id)
    await update_node_status(node_id, "skipped", metadata={"skipped_reason": reason})
    
    # 重新计算就绪节点
    await dag_scheduler.recompute_ready_nodes(task_id)
    
    return {"success": True, "node_id": node_id, "new_status": "skipped"}
```

---

## 5️⃣ 实时反馈诊断

### 现状

```
WebSocket 连接
  ↓
/ws/task/{task_id}
  ├─ 轮询获取 task 和 task_node 状态 (每 1-2s)
  ├─ 检查 Redis Stream task:{task_id}:events (XREAD)
  └─ 组装并发送 JSON 到前端
  
前端接收
  └─ 展示进度条 / 日志 / 实时预览
  
消息类型
  ├─ node_update: 节点状态变化
  ├─ log: Agent 执行日志
  ├─ task_done: 任务完成
  ├─ agent_status: Agent 心跳
  └─ (缺失很多细节)
```

### 发现的问题

| # | 问题 | 影响 | 严重度 |
|---|------|------|--------|
| 1 | **轮询延迟 1-2s** | 实时性不够；特别是对快速任务（如检查语法），用户感觉不到进度 | 中 |
| 2 | **消息类型不齐全** | 缺少"章节预览""审查反馈""错误详情"等关键信息 | 中-高 |
| 3 | **没有消息确认机制** | WebSocket 发送后不知道前端是否收到；网络抖动时可能丢消息 | 中 |
| 4 | **实时预览功能缺失** | 用户无法看到当前已写出的章节内容，只能等最后生成 | 高 |
| 5 | **错误信息不详细** | 只说"failed"，不说失败原因 / 堆栈 / 建议 | 中 |
| 6 | **WebSocket 连接管理不明确** | 连接断开后是否自动重连？有无连接池限制？ | 中 |
| 7 | **没有优先级消息队列** | 关键消息（如错误）和普通消息（如日志）同等权重；易被淹没 | 中 |

### 根因分析

1. **轮询而非事件驱动**：最根本的架构问题
2. **消息协议过简**：消息类型不足，无法表达丰富的业务场景
3. **可观测性缺失**：没有专门的"用户关心信息"流

### 优化方案

#### 方案 A：事件驱动实时推送

```python
# 在 FSM 和 DAG Scheduler 中触发事件

class RealtimeEventPublisher:
    """实时事件发布器"""
    
    async def publish_node_update(self, task_id: UUID, node_id: UUID, status: str):
        await redis.xadd(f"task:{task_id}:realtime", {
            "type": "node_update",
            "node_id": str(node_id),
            "status": status,
            "timestamp": now().isoformat(),
        })
    
    async def publish_chapter_preview(self, task_id: UUID, chapter_id: str, content: str):
        await redis.xadd(f"task:{task_id}:realtime", {
            "type": "chapter_preview",
            "chapter_id": chapter_id,
            "content": content[:500],  # 限制大小
            "timestamp": now().isoformat(),
        })
    
    async def publish_error(self, task_id: UUID, error: Exception, node_id: UUID = None):
        await redis.xadd(f"task:{task_id}:realtime", {
            "type": "error",
            "node_id": str(node_id) if node_id else None,
            "error_message": str(error),
            "error_type": error.__class__.__name__,
            "timestamp": now().isoformat(),
        })

# 使用示例
publisher = RealtimeEventPublisher()
try:
    result = await writer.write_chapter(node_id, context)
    await publisher.publish_node_update(task_id, node_id, "done")
    await publisher.publish_chapter_preview(task_id, node_id, result)
except Exception as e:
    await publisher.publish_error(task_id, e, node_id)
    await publisher.publish_node_update(task_id, node_id, "failed")
```

#### 方案 B：完整的消息类型定义

```python
class RealtimeMessage(BaseModel):
    """实时推送消息规范"""
    
    type: Literal[
        "node_start",           # 节点开始执行
        "node_complete",        # 节点完成
        "node_failed",          # 节点失败
        "chapter_preview",      # 章节实时预览
        "review_score",         # 审查评分
        "consistency_issue",    # 一致性问题
        "state_transition",     # FSM 状态转移
        "error",                # 系统错误
        "progress",             # 进度更新
        "agent_status",         # Agent 状态变化
    ]
    
    timestamp: datetime
    task_id: UUID
    node_id: UUID = None
    
    # 具体数据（根据 type 填充）
    data: dict  # 灵活字段
    
    # 可选：错误追踪
    error_id: str = None  # 用于用户反馈时引用
    
    # 可选：优先级
    priority: Literal["low", "normal", "high"] = "normal"
    
    class Config:
        use_enum_values = True

# 具体示例
msg1 = RealtimeMessage(
    type="chapter_preview",
    task_id=task_id,
    node_id=node_id,
    data={
        "chapter_title": "第一章",
        "content": "这是章节的部分内容...",
        "progress_percent": 45,
    },
    priority="normal",
)

msg2 = RealtimeMessage(
    type="review_score",
    task_id=task_id,
    node_id=node_id,
    data={
        "score": 82,
        "pass": True,
        "feedback": "逻辑清晰，可再补充示例",
    },
    priority="high",
)

msg3 = RealtimeMessage(
    type="error",
    task_id=task_id,
    node_id=node_id,
    data={
        "message": "LLM 调用超时，已重试 1/3 次",
        "retry_count": 1,
        "next_retry_at": "2026-05-03T12:05:00Z",
    },
    priority="high",
    error_id="err_20260503_xyz",
)
```

#### 方案 C：消息确认机制

```python
# WebSocket handler 中
@app.websocket("/ws/task/{task_id}")
async def websocket_task_updates(websocket: WebSocket, task_id: UUID):
    await websocket.accept()
    
    # 服务端记录已发送消息
    sent_messages = {}  # msg_id -> message
    ack_timeout = 30  # 30s 内必须收到 ACK
    
    # 发送消息
    async def send_with_ack(message: RealtimeMessage) -> bool:
        msg_id = str(uuid.uuid4())
        envelope = {
            "msg_id": msg_id,
            "type": "message",
            "data": message.dict(),
        }
        
        sent_messages[msg_id] = (message, time.time())
        
        try:
            await websocket.send_json(envelope)
            
            # 等待 ACK（超时则重发）
            ack_received = asyncio.Event()
            
            async def wait_for_ack():
                while time.time() - sent_messages[msg_id][1] < ack_timeout:
                    # 在主循环中检查是否收到 ACK
                    await asyncio.sleep(0.1)
                if msg_id in sent_messages:
                    # 未收到 ACK，标记为可重发
                    logger.warn(f"No ACK for message {msg_id}")
                    return False
                return True
            
            return await wait_for_ack()
            
        except Exception as e:
            logger.error(f"Failed to send message {msg_id}: {e}")
            return False
    
    # 监听 Redis 事件并推送
    async def stream_updates():
        last_id = "0"
        while websocket.client_state == WebSocketState.CONNECTED:
            try:
                messages = await redis.xread(
                    f"task:{task_id}:realtime", 
                    last_id, 
                    count=10,
                    block=1000  # 最多等 1s
                )
                
                for msg_id, msg_data in messages:
                    message = RealtimeMessage(**msg_data)
                    await send_with_ack(message)
                    last_id = msg_id
                    
            except Exception as e:
                logger.error(f"Stream update error: {e}")
                await asyncio.sleep(1)
    
    # 监听客户端 ACK
    async def listen_for_acks():
        while websocket.client_state == WebSocketState.CONNECTED:
            try:
                data = await websocket.receive_json()
                if data.get("type") == "ack":
                    msg_id = data.get("msg_id")
                    if msg_id in sent_messages:
                        del sent_messages[msg_id]  # 移除已 ACK 的消息
            except Exception as e:
                logger.error(f"ACK listen error: {e}")
                await asyncio.sleep(1)
    
    # 并行运行
    tasks = [
        asyncio.create_task(stream_updates()),
        asyncio.create_task(listen_for_acks()),
    ]
    
    try:
        await asyncio.gather(*tasks)
    finally:
        await websocket.close()
```

#### 方案 D：实时章节预览

```python
# Writer Agent 中
class WriterAgent(BaseAgent):
    async def handle_task(self, ctx: dict[str, Any]) -> str:
        task_id = ctx["task_id"]
        node_id = ctx["node_id"]
        chapter_title = ctx["title"]
        
        # 1. 准备写作上下文
        outline = await get_outline(task_id)
        memory = await session_memory.query(task_id)
        
        # 2. 调用 LLM（流式）
        full_content = ""
        chunk_buffer = ""
        
        async for chunk in self.llm_client.chat_stream(
            system=...,
            messages=...,
        ):
            full_content += chunk
            chunk_buffer += chunk
            
            # 每累积 200 字发送一次预览
            if len(chunk_buffer) >= 200:
                await self.publisher.publish_chapter_preview(
                    task_id,
                    chapter_title,
                    full_content,
                )
                chunk_buffer = ""
        
        # 最后一次预览
        await self.publisher.publish_chapter_preview(
            task_id,
            chapter_title,
            full_content,
        )
        
        return full_content
```

#### 方案 E：错误详情和建议

```python
class DetailedError(BaseModel):
    """详细的错误信息"""
    
    error_id: str  # 用于用户反馈
    error_type: str  # LLMError, TimeoutError, ValidationError ...
    message: str  # 用户友好的消息
    
    # 技术细节
    technical_details: str = None  # 堆栈跟踪
    
    # 建议
    suggestion: str  # 用户可能的解决办法
    
    # 重试信息
    retryable: bool
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: datetime = None
    
    # 上下文
    affected_node_id: UUID = None
    affected_node_title: str = None

# 使用
try:
    result = await writer.write_chapter(...)
except TimeoutError as e:
    error = DetailedError(
        error_id=str(uuid.uuid4()),
        error_type="TimeoutError",
        message="章节写作超时，系统已触发重试",
        technical_details=traceback.format_exc(),
        suggestion="如果问题持续，可尝试：1) 减少字数要求 2) 检查网络连接",
        retryable=True,
        retry_count=1,
        max_retries=3,
        next_retry_at=now() + timedelta(seconds=5),
    )
    
    await publisher.publish_error_details(task_id, error)
```

---

## 📋 优化优先级排序

### P0（必做，影响系统稳定性）
1. 多层状态不同步 → 引入 StateStore (方案 4A)
2. DB 查询无乐观锁 → 加 version 列 (方案 2A)
3. SessionMemory 内存丢失 → Redis 持久化 (方案 2C)
4. Writer 并发无上限 → 引入 WriterPool (方案 3B)

### P1（应做，改进实时性和可观测性）
5. 轮询改事件驱动 → Redis Stream 监听 (方案 1B, 5A)
6. 消息类型不齐全 → 定义完整协议 (方案 5B)
7. Agent 启动无检查 → 加健康检查 (方案 3D)
8. FSM 和 DAG 交叉 → 分离 FlowController (方案 1A)

### P2（可做，提升用户体验和运维能力）
9. 没有状态转移日志 → 加 audit 表 (方案 4D)
10. 无法手动干预 → 加 force-transition API (方案 4E)
11. 章节预览缺失 → 实现流式预览 (方案 5D)
12. 错误信息不详细 → DetailedError 模型 (方案 5E)

---

## 🎯 后续行动方案

### 第一周（P0）
- [ ] 审视并确认 StateStore 设计
- [ ] 在 TaskNode 加入 version 列（DB 迁移）
- [ ] 实现 SessionMemory Redis 持久化
- [ ] 构建 WriterPool 限流控制

### 第二周（P1）
- [ ] 重构 DAG Scheduler 为事件驱动（从轮询 → XREAD）
- [ ] 定义 RealtimeMessage 协议
- [ ] 实现 Agent 健康检查
- [ ] 分离 FlowController

### 第三周（P2）
- [ ] 添加 StateTransitionLog 表和审计
- [ ] 实现手动干预 API
- [ ] 集成章节流式预览
- [ ] 构建详细错误信息体系

---

## 📊 预期收益

| 改进维度 | 当前状态 | 改进后 | 提升幅度 |
|---------|--------|--------|---------|
| **延迟** | 1-2s 轮询周期 | <100ms 事件驱动 | **95% ↓** |
| **并发** | 无限 Writer | 受 Token 限制 | 可控且稳定 |
| **可恢复性** | 简陋 checkpoint | 完整快照+日志 | **100% 还原** |
| **可观测性** | 只有日志 | 日志+事件+审计 | 故障排查 **10x 快** |
| **用户体验** | 无预览、无反馈 | 实时预览+错误详情 | 满意度 **↑** |

