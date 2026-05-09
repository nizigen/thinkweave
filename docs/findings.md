# findings.md — 研究发现与技术决策知识库

## 2026-05-09：Phase 7-05 MCP 接入执行决策

- 执行形态：采用“网关内建工具 + 配置驱动服务识别”的最小可运行方案，避免首轮直接绑定外部 SDK 造成依赖链不稳定。
- 生命周期语义落地：
  - `llm_client.chat_with_tools` 在 MCP 执行开启时，会把 `mcp.*` 工具调用推进到 `registered -> running -> success|failed -> cleaned`。
  - lifecycle metadata 新增 `source=mcp`、`server_name` 等字段用于 Redis 事件流观测。
- researcher 实际接入：
  - `WorkerAgent` 仅在 `researcher + ENABLE_MCP_GATEWAY=true` 时走工具辅助路径，其他角色不受影响。
  - 工具输出以文本上下文回灌后再走普通 `chat` 生成 researcher JSON，降低 provider 对“tool message schema”差异带来的风险。
- 配置热更新策略：
  - `mcp_gateway` 使用配置指纹（`mtime_ns + size`）失效缓存，解决仅靠 mtime 可能漏刷新的问题。
- 安全边界：
  - 角色白名单默认仅 researcher。
  - filesystem 工具必须配置 `MCP_FILESYSTEM_ROOTS`，且严格路径白名单校验。
  - 任一 MCP 调用异常均以 fail-safe 处理，不中断主 DAG 运行。

## 2026-05-09：DeerFlow 2.0 MCP 调研结论与 thinkweave 接入策略

- DeerFlow 2.0 可借鉴的实现要点（来自其 backend 文档与开发指南）：
  - 多 server 管理 + 懒加载（首次使用再初始化工具）。
  - 配置变更触发缓存失效（通过配置文件变更检测刷新工具清单）。
  - 支持 stdio / SSE / HTTP 传输与 OAuth（HTTP/SSE）扩展能力。
  - 在工具数量较大时采用“先搜索、后激活”思路，避免一次性注入全部工具导致上下文膨胀。
- MCP 官方 servers 仓库结论：
  - reference servers 主要是示例实现，不应直接等同生产级安全方案。
  - TypeScript server 可 `npx` 运行，Python server 可 `uvx` / `pip` 运行，适合本项目做可控 PoC。
- 与当前 thinkweave 架构的契合点：
  - 我们已有 `TEA envelope + ToolLifecycleService + ToolManagerAgent`，可直接承接 MCP 生命周期可观测性。
  - 我们已有开关体系，能把 MCP 放入灰度与回滚通道，不需要改动 DAG/FSM 主链路。
- 本轮选型决策（先小后大）：
  - 必选：`mcp-server-fetch`、`mcp-server-time`
  - 可选：`mcp-server-filesystem`（只读白名单）
  - 暂缓：高权限/高副作用 server（写库、浏览器自动化、git 写操作）
- 风险控制决策：
  - 首轮仅开放 `researcher` 角色使用 MCP。
  - 任何 MCP 异常 fail-safe，不中断任务主流程。
  - 通过 `tool_lifecycle(source=mcp)` 事件作为上线与回归准入标准。

## 2026-05-08：Phase 7 Code Review Fix 决策补充

- 修复策略：优先修“语义错误 + 未接线能力 + 容错可观测性 + 内存边界”四类问题，保持行为兼容优先。
- 关键修正：
  - 工具生命周期 `success` 只应由真实执行完成路径产生，`chat_with_tools` 仅标记到 `running`。
  - `dag_recomposer.reconnects` 必须在调度器落地执行，避免“计划存在但执行缺失”。
  - 控制面协议对未知 action fail-fast，避免 silent fallback 误导调用方。
  - in-memory 账本必须有上限，避免长会话内存漂移。

## 2026-05-08：Phase 7-4 动态 DAG 重组实现决策

- 决策：在已有 `_inject_consistency_repair_wave` 路径上引入 `dag_recomposer`，先做“结构化计划化”而不是新增并行重组入口。
- 原因：
  - 一致性失败后本就存在修复波次注入逻辑，是最低风险的 runtime 重组切入点。
  - 先把插入和重连显式化（`insertions + reconnects`）可为后续 SSI 驱动自动重组打基础。
- 实现要点：
  - `dag_recomposer` 负责目标归一化、波次上限、模式判定、依赖重连描述；
  - `dag_scheduler` 只负责 materialization 与状态推进，不再内联重组策略细节。
- 风险控制：
  - 保持标题/角色/状态命名约定不变，兼容现有 UI/事件/测试消费；
  - 注入依赖通过 logical-id 两阶段映射，避免先后顺序导致的依赖丢失。

## 2026-05-08：Phase 7-3 Tool 生命周期实现决策（无 MCP）

- 决策：先落地 `ToolLifecycleService + ToolManagerAgent` 内生闭环，不把 MCP 作为依赖前提。
- 原因：现有主链路已经有 `chat_with_tools` 与 Redis Streams 事件通道，先做可观测生命周期比先接外部工具生态更稳。
- 风险控制：
  - `ENABLE_TOOL_LIFECYCLE=false` 默认关闭，避免影响现有任务执行；
  - `ENABLE_TOOL_MANAGER_AGENT=false` 默认关闭，仅在显式启用后实例化 `tool_manager` 角色；
  - `_build_runtime_agent` 属高影响符号，仅追加最小分支，不改原角色分发逻辑。
- 生命周期语义（当前基线）：
  - `registered -> running -> success|failed -> cleaned`
  - `chat_with_tools` 当前仅做 telemetry（记录模型选出的 tool_calls），不接管真实工具执行控制流。

## 2026-05-08：Phase 7 方案可行性与边界决策（HALO / AgentOrchestra / DAGAgent / WorFBench）

- 可行性结论：
  - `MCTS(HALO)`：可落地，但应先 Shadow（仅评分记录，不接管调度）。
  - `TEA(AgentOrchestra)`：适合当前消息层（`redis_streams.MessageEnvelope`）演进为类型化协议。
  - `动态DAG重组(DAGAgent+WorFBench)`：应复用现有 `dag_scheduler.py` 的波次注入能力，避免重复造轮子。
- 关键落地顺序（风险从低到高）：
  - `TEA协议+dag_eval基线 -> MCTS Shadow -> ToolManagerAgent -> 动态DAG重组在线化`。
- 本轮执行边界（用户确认）：
  - 由于历史 MCP 稳定性问题，Phase 7 首轮 **不把 MCP 作为前置依赖**。
  - 先确保“无 MCP 依赖”的可运行闭环，再评估是否引入工具生态统一层。

## 2026-05-08：MCTS Shadow 落地口径

- 当前实现是 `Shadow only`：
  - 仅在 `decomposition_trace.strategy_trace` 输出 5 候选 UCB 评分轨迹；
  - 不改 DAG 结构，不改 scheduler dispatch，不改任务执行顺序。
- 候选策略固定 5 类：`reliability_first / balanced_flow / evidence_intensive / chapter_parallel / fast_compact`。
- 可复现性策略：随机扰动由 `title|mode|depth|target_words` 作为 seed 固定，保证同输入可复现。

## 2026-03-22：Aletheia 实施计划借鉴（已纠偏）

- 借鉴点：
  - 两层记忆推进：SessionMemory 先落地，KnowledgeGraph 后接入。
  - 在现有运行时流程中挂 memory hooks，而不是扩展过多新编排节点。
  - 生命周期合同：`initialize -> store/query -> cleanup -> promote handoff`。
- 本仓库纠偏：
  - 本地可用基线为 `cognee==0.5.5`。
  - 默认 provider 目标为 `graph=kuzu`、`vector=lancedb`。
  - `neo4j/qdrant` 不作为本仓库当前默认 runtime backend。

## 竞品与参考项目研究

### 多Agent编排系统（2026-03-06）

| 项目 | 借鉴点 | 不借鉴 |
|------|--------|--------|
| **AgentOrchestra** (arXiv 2506.12508) | 动态规划、GAIA基准 | 成本过高($292/任务)、两层结构 |
| **MetaGPT** | SOP驱动角色分工 | 固定SOP流程，不够灵活 |
| **Chain-of-Agents** (Google NeurIPS 2024) | 解决 Lost-in-the-Middle | 线性链不支持并行 |
| **DeerFlow** (ByteDance) | 中间件管道/并发控制/输入验证/Token追踪/模型配置化 | LangChain依赖 |

### Aletheia v2 架构研究（2026-03-18）

**来源文档**：`C:/GitHub/Aletheia/docs/specs/2026-03-17-*.md`

| 模块 | 可复用设计 | 适配要点 |
|------|-----------|---------|
| **Memory Layer** | Session Memory (单任务去重) + Knowledge Graph (跨任务积累) | 用 MemoryMiddleware 替代 LangGraph node 层注入 |
| **Skill Registry** | applies_to + trigger.keywords + priority 匹配 | v2 迭代考虑增强现有 skills 系统 |
| **Quality Pipeline** | 分层质量检查 (Verifier → Compliance → Devil's Advocate) | v1 用 Reviewer + Consistency 覆盖；v2 按体裁插入专用 Agent |
| **cognee vendor** | add()/search()/cognify() API + Neo4j/Qdrant adapter | 移除 cognee 配置系统/LLM provider，替换为项目自有 |

### cognee 技术评估（2026-03-18）

- **核心 API**：`add()` (数据写入 graph+vector)、`search()` (graph/vector/hybrid 检索)、`cognify()` (原始数据→结构化知识)
- **存储后端**：Neo4j (图) + Qdrant (向量)，可通过 namespace 隔离多 session
- **集成方式**：vendor 核心模块 ~500-800 LOC（待 Step 4.1a spike 确认）
- **风险**：`cognify()` 内部是多步 pipeline，可能依赖 cognee 自己的 LLM provider
- **降级方案**：Session Memory 用 dict + asyncio.Lock；Knowledge Graph 用 EvidenceStore + pgvector

---

## 技术栈决策

### 向量数据库选型（2026-03-07 + 2026-03-18）

| 方案 | 用途 | 理由 |
|------|------|------|
| **pgvector** (保留) | RAG 检索（文档分块检索） | 复用 PG，零新基础设施，项目规模 sub-100K 向量足够 |
| **Qdrant** (新增) | 记忆层向量检索/去重 | cognee 原生支持，章节级嵌入+相似度搜索，namespace 隔离 |
| 不用 ChromaDB | — | 需要额外进程，pgvector 已覆盖 RAG 需求 |
| 不用 FAISS | — | 内存索引，不持久化 |

### 图数据库选型（2026-03-18）

| 方案 | 理由 |
|------|------|
| **Neo4j** (选用) | cognee 原生支持，ACID 事务，Cypher 查询语言成熟，社区版免费 |
| 不用 ArangoDB | 多模型但社区较小 |
| 不用纯 PG 图查询 | 递归 CTE 可以做简单图遍历，但多跳关系查询太慢 |

### Prompt 模板管理（2026-03-07）

- 选用 `str.format_map()`（纯 Python）
- 不用 Jinja2（TECH_STACK 约束）
- 不用 LangChain PromptTemplate（禁止 LangChain）
- 模板文件路径：`prompts/{role}/{action}.md`

### 导出工具（2026-03-06）

- PDF：reportlab（纯 Python，Windows 友好）
- Word：python-docx
- 不用 weasyprint（需要 GTK 运行时，Windows 配置复杂）

---

## 资源链接

| 资源 | URL / 路径 |
|------|-----------|
| Aletheia v2 架构设计 | `C:/GitHub/Aletheia/docs/specs/2026-03-17-aletheia-v2-architecture-design.md` |
| Aletheia Memory Layer 设计 | `C:/GitHub/Aletheia/docs/specs/2026-03-17-memory-layer-design.md` |
| cognee GitHub | https://github.com/topoteretes/cognee |
| DeerFlow GitHub | https://github.com/bytedance/deer-flow |
| Chain-of-Agents 论文 | Google NeurIPS 2024 |
| AgentOrchestra 论文 | arXiv 2506.12508 |
