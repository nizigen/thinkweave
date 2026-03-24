# findings.md — 研究发现与技术决策知识库

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
