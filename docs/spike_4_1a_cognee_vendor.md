# Spike Report: Step 4.1a — cognee vendor 验证

**日期**: 2026-03-19
**结论**: **vendor 不可行 — 改为直接 pip install cognee + 薄适配层**

---

## 1. 调研范围

对 [cognee](https://github.com/topoteretes/cognee)（GitHub ~6,829 stars）进行 vendor 可行性评估，目标是提取 `add()`/`search()`/`cognify()` 三个核心 API + Neo4j/Qdrant 客户端封装，放入 `app/memory/_vendor/`（目标 500-800 LOC）。

评估版本：
- **cognee v0.1.21**（原计划 vendor 基线，2025-01-10 发布，wheel ~471 KB）
- **cognee v0.5.5**（当前最新，2026-03-14 发布，wheel ~1.64 MB）

---

## 2. 关键发现

### 2.1 依赖链过深 — 超出 1500 LOC 阈值

| 版本 | 核心依赖数 | 重量级依赖 |
|------|-----------|-----------|
| v0.1.21 | ~35 | pandas, datasets, nltk, scikit-learn, matplotlib, transformers, bokeh |
| v0.5.5 | ~40+ | litellm, kuzu, lancedb, fastembed, onnxruntime, rdflib |

cognee 内部模块深度耦合：`cognify()` → `extract_graph_from_data` → `LLMGateway` → `litellm/instructor` → 配置系统 → 工厂函数。提取任意一个 API 都会拖出整条依赖链。

**结论：vendor ~500-800 LOC 不可行，实际需要 >3000 LOC + 多个重量级依赖。**

### 2.2 cognee 没有 Qdrant 适配器

原计划 vendor cognee 的 Qdrant 客户端封装。实际调研发现：
- cognee **默认使用 LanceDB**（文件级向量数据库）
- 内置适配器：LanceDB / PGVector / ChromaDB / Neptune Analytics
- **Qdrant 不在内置适配器中**

**结论：Qdrant 适配器必须自研。**

### 2.3 cognify() 实体提取 = LLM 结构化输出

cognify() 的核心实体提取完全基于 LLM 调用：

```python
# cognee 的 KnowledgeGraph 数据模型
class Node(BaseModel):
    id: str
    name: str
    type: str
    description: str

class Edge(BaseModel):
    source_node_id: str
    target_node_id: str
    relationship_name: str

class KnowledgeGraph(BaseModel):
    nodes: List[Node]
    edges: List[Edge]
```

通过 `LLMGateway.acreate_structured_output()` 将文本发给 LLM，要求返回符合 `KnowledgeGraph` schema 的 JSON。

**结论：可用项目已有的 `llm_client.chat_json()` 完全替代，无需 vendor cognee 的 LLM provider。**

### 2.4 cognee 架构模式值得借鉴

虽然不 vendor 代码，但 cognee 的架构设计可作为自研参考：

| 模式 | cognee 实现 | 本项目借鉴方式 |
|------|------------|--------------|
| 图数据库 ABC | `GraphDBInterface`（~20 个 async 方法） | 精简为 ~8 个核心方法 |
| 向量数据库 Protocol | `VectorDBInterface`（Protocol 结构化类型） | 采用 ABC，~6 个核心方法 |
| 配置管理 | `pydantic-settings` + `@lru_cache` 单例 | 已有 `MemoryConfig` 计划，采用相同模式 |
| 适配器工厂 | 工厂函数 + if/elif 分发 | 简化为直接构造（只需 2 个后端） |
| 数据载体 | `DataPoint`（Pydantic BaseModel，统一 ID/type/metadata） | 采用类似模式 |
| Neo4j 操作 | `MERGE` upsert + `__Node__` 基础标签 + 类型标签 | 直接参考 |
| 实体提取 | LLM 结构化输出 + 后处理验证 | 用 `chat_json()` 实现 |

### 2.5 cognee GraphDBInterface 核心方法

精简后适合本项目的子集：

```
add_node(node)          — 单节点 upsert
add_nodes(nodes)        — 批量节点 upsert
add_edge(src, tgt, rel) — 单边 upsert
add_edges(edges)        — 批量边 upsert
get_node(node_id)       — 获取节点
get_neighbors(node_id)  — 获取邻居
query(cypher, params)   — 原始 Cypher 查询
delete_graph()          — 清空图
```

### 2.6 cognee VectorDBInterface 核心方法

精简后适合本项目的子集：

```
create_collection(name)           — 创建集合
create_data_points(name, points)  — 插入向量
search(name, query_vector, limit) — 相似度搜索
delete_data_points(name, ids)     — 删除向量
has_collection(name)              — 检查集合存在
```

---

## 3. 决策：直接 pip install cognee + 薄适配层

vendor 不可行，但 cognee 的 `add()`/`search()`/`cognify()` API 本身设计简洁。改为直接 `pip install cognee==0.1.21`，通过薄适配层封装对接项目配置和 LLM 客户端。

### 方案概要

| 组件 | 说明 |
|------|------|
| `pip install cognee==0.1.21` | 直接使用 cognee 包，通过环境变量覆盖其配置 |
| `memory/config.py` | MemoryConfig（pydantic-settings），设置 cognee 环境变量 |
| `memory/adapter.py` | 薄适配层：封装 cognee.add/search/cognify，对接项目配置 |
| `memory/models.py` | 项目侧数据模型（TopicClaim/ContentSummary/EntityRelation） |
| `memory/embedding.py` | 复用 llm_client.embed()，带 SHA256 缓存 |
| `memory/image_registry.py` | 图片 URL→章节映射，asyncio.Lock 保护 |
| `memory/session.py` | SessionMemory 统一 API，内部调用 cognee adapter |

### 优势

1. **复用成熟实现**：cognee 的图构建、实体提取、检索已经过社区验证
2. **最小适配成本**：薄适配层 ~200 LOC，远少于自研 ~880 LOC
3. **优雅降级保留**：MEMORY_ENABLED=false 跳过所有 cognee 调用

### 对 Step 4.1b 的影响

- **新增依赖**：`pip install cognee==0.1.21`（含 neo4j、qdrant-client 等传递依赖）
- **新增**：`app/memory/adapter.py`（cognee 薄适配层）
- **移除**：自研 `graph_store.py`、`vector_store.py`、`entity_extractor.py`（由 cognee 内部处理）
- **保留**：Docker Compose 添加 Neo4j + Qdrant、config.py、models.py、session.py、image_registry.py、embedding.py

---

## 4. 版本记录

| 项目 | 值 |
|------|-----|
| cognee 评估版本 | v0.1.21 (wheel 471KB) + v0.5.5 (wheel 1.64MB) |
| cognee GitHub | https://github.com/topoteretes/cognee |
| 评估日期 | 2026-03-19 |
| 决策 | 不 vendor，改用 pip install cognee==0.1.21 + 薄适配层 |
| 参考架构 | cognee GraphDBInterface / VectorDBInterface / KnowledgeGraph 数据模型 |
