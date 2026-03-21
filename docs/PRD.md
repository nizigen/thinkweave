# PRD.md — 产品需求文档

## 项目概述

**项目名称**：层级化Agent编排与长文本控制系统
---

## 1. 产品定位

构建一个支持层级化多Agent协作的智能编排平台，核心能力是将复杂任务（如生成万字技术报告、长篇小说）分解为结构化子任务DAG，由多层Agent协同执行，最终输出结构完整、内容连贯的长文本。

目标用户：需要自动化生成长篇结构化文档的研究人员、技术团队。

---

## 1.1 竞品分析

| 系统 | 架构模式 | 核心能力 | 局限性 |
|------|----------|----------|--------|
| **AgentOrchestra**（arXiv 2506.12508） | 两层：Planning Agent + 专用Sub-Agent | GAIA基准89%准确率；动态规划 | 单任务平均成本$292；两层结构缺乏中间管理层 |
| **MetaGPT** | SOP驱动，角色分工（PM/架构师/工程师） | 模拟软件开发团队，减少逻辑错误；结构化角色协作 | 固定SOP流程，难以动态适应非软件开发任务 |
| **CrewAI** | 角色基团队（Crew+Flow双层） | 40+内置工具；已支持A2A协议；双层编排 | 以研究/内容生成场景为主，通用编排能力有限 |
| **AutoGen**（Microsoft） | 对话驱动，Core+AgentChat双层 | 支持human-in-the-loop；灵活的对话模式 | 对话驱动难以精确控制执行顺序和依赖关系 |
| **LangChain Open Deep Research** | Supervisor-Researcher多Agent并行 | 并行研究+长报告生成 | 领域专用（研究报告），非通用编排平台 |
| **GPT Researcher** | planner+execution agents | 支持tree-structured探索；输出5-6页报告 | 输出限于报告体裁；不支持任意长文本结构 |
| **Chain-of-Agents**（Google NeurIPS 2024） | Worker链式传递+Manager汇总 | 解决Lost-in-the-Middle问题；适合长文本处理 | 线性链结构，不支持DAG并行任务调度 |

### 差异化定位

本系统与上述竞品的核心差异点：

1. **三层结构 vs. 两层结构**：不同于AgentOrchestra的编排+执行两层，本系统采用编排层/管理层/执行层三层架构，支持更细粒度的管控与中间层任务协调。
2. **动态DAG vs. 固定SOP**：不同于MetaGPT的固定SOP流程，本系统采用LLM动态分解+DAG调度，可适应任意结构的复杂任务，不局限于软件开发场景。
3. **通用平台 vs. 垂直工具**：不同于Open Deep Research / GPT Researcher的搜索+报告专用模式，本系统是通用编排平台，长文本生成只是核心验证场景之一。
4. **Chain-of-Agents借鉴**：参考Chain-of-Agents的Worker-Manager模式，将其应用于长文本分段生成，写作Agent链式传递上下文摘要，解决"中间内容丢失"问题。

---

## 2. 功能需求

### 2.1 核心功能（必须实现）

#### F1 — Agent管理模块
- 支持Agent注册：名称、角色类型、能力描述、所属层级
- 支持Agent动态上线/下线，查看当前在线Agent列表
- 支持Agent能力标签（如：规划、撰写、审查、工具调用）
- Agent状态追踪：空闲 / 运行中 / 失败

#### F2 — 任务编排引擎

**生成模式**：
- **技术报告**：预设学术/技术文档结构（背景→现状→方法→实验→结论）
- **小说**：预设叙事结构（设定→发展→高潮→结局）
- **自定义**：用户可选择预设模板（论文、商业计划书等），也可自由描述想要的结构

**研究深度**（同时控制DAG粒度和生成字数）：
- **快速**：3-5个子任务，目标3000字
- **标准**（默认）：6-10个子任务，目标10000字
- **深入**：10+个子任务，目标20000字

- 用户输入自然语言任务描述，系统调用LLM自动分解为子任务DAG
- 任务分解采用few-shot prompt + JSON Schema约束输出，确保结构化可解析
- DAG节点属性：任务ID、描述、负责Agent、前置依赖、状态
- 支持并行执行无依赖节点，串行执行有依赖节点
- DAG调度使用Redis Sorted Set按优先级排序就绪节点，实现优先级感知调度
- 支持动态DAG更新：执行中途可插入新节点或修改依赖关系（参考AgentOrchestra的adaptive planning）
- 支持任务动态重分配：当执行Agent失败时，自动将任务转移给备用Agent
- 任务状态机：待执行 → 执行中 → 已完成 / 失败 → 重试

#### F3 — 通信中间件
- 使用Redis Streams（而非Pub/Sub）作为主要消息通道，支持消费者组、消息持久化和断点续消费
- 消息格式：JSON结构化，含 task_id、from_agent、to_agent、content、timestamp
- 支持广播消息（层级内通知）和点对点消息
- Redis Sorted Set管理定时任务和超时检测，按截止时间排序扫描到期任务
- 分布式锁（SETNX+TTL）防止任务重复分配，确保同一任务仅被一个Agent领取
- 消息持久化到PostgreSQL，支持历史回溯

#### F4 — 长文本控制模块
长文本生成分为五个阶段，每阶段由专用Agent负责：
1. **大纲Agent**：接收用户主题，生成带章节结构的大纲（Markdown格式），每章设计为尽量独立，明确章节边界和衔接要点
2. **用户确认大纲**：用户可在线编辑大纲（富文本树形编辑器，可拖拽调整章节顺序），确认后进入写作阶段
3. **写作Agent（多实例）并行撰写**：各章节内容基于大纲约束并行生成，每个Writer拿到完整大纲 + 自己负责的章节描述。借鉴Chain-of-Agents思想，大纲中包含章节间衔接要点（context bridges）+ **主题领地声明（topic_claims：每章 owns 什么论点、boundary 不覆盖什么）**，确保并行写作的各章节在逻辑上可衔接且内容不重复。写作前通过 Session Memory 获取其他已完成章节的摘要，避免内容重复
4. **审查Agent**：对每章内容进行独立LLM调用，执行事实核查和质量评分（0-100分），**同时通过 Session Memory 检测与其他章节的内容重叠度（向量相似度 > 0.85）**，低于70分或检测到严重重叠则退回对应写作Agent重写（最多3次）
5. **一致性Agent**：**从 Session Memory 读取各章节摘要**（而非全文扫描，降低 token 消耗），指出跨章节问题（风格不统一、逻辑矛盾、重复内容），生成问题清单发给对应写作Agent修改；维护全局上下文窗口（包含摘要+关键实体列表），确保跨章节引用一致。修改后再次检查，最多循环2次

生成流程由有限状态机（FSM）管理：
```
INIT → OUTLINE → OUTLINE_REVIEW → WRITING → REVIEWING → CONSISTENCY → DONE
                                     ↑___________|（审查不通过回写作，最多3次）
                                     ↑__________________________|（一致性不通过回写作，最多2次）
```

#### F5.5 — 记忆协调模块（Memory Layer）

解决并行写作中的核心痛点：多个写作Agent互不知道对方写了什么，导致内容重复 20-30%。同时建立跨任务知识积累能力。

**Session Memory（单次任务记忆）**：
- 大纲Agent生成章节结构时，分配**主题领地**（topic territory）：每章声明 owns（负责的论点）和 boundary（不覆盖的内容）
- 写作Agent开始前，查询其他已完成章节的内容摘要、已用图片、已用引用，避免重复
- 写作Agent完成后，立即将本章摘要（key_points + word_count + used_evidence）写入 Session Memory
- 审查Agent审查时，自动检测当前章节与其他章节的**语义重叠度**（向量相似度 > 0.85 标记为重复）
- 一致性Agent可直接读取所有章节摘要，无需全文扫描

**Knowledge Graph（跨任务知识图谱）**：
- 任务完成后，将已验证的引用、术语定义、实体关系（如"量子纠缠→量子通信→应用场景"）提升到持久化知识图谱
- 新任务启动时，查询历史知识图谱，获取已验证的参考资料和实体关系，减少重复研究
- 知识图谱条目 90 天后标记为 stale，需重新验证

**四级去重级联**：
1. **Level 0 — 大纲领地分配**：Outline Agent 在大纲中明确每章的主题边界
2. **Level 1 — 写作前上下文注入**：Writer 启动前读取其他章节已写内容摘要
3. **Level 2 — 写作后重叠检测**：Writer 完成后，用向量相似度检测与其他章节的内容重叠
4. **Level 3 — 审查/一致性兜底**：Reviewer + Consistency Agent 最终把关

**优雅降级**：
- Neo4j 不可用 → 退回到内存 dict 存储主题领地（丢失图查询，基础去重仍工作）
- Qdrant 不可用 → 退回到 numpy 暴力余弦相似度（小规模任务可接受）
- 记忆模块整体可通过 `MEMORY_ENABLED=false` 关闭，退回 v1 行为

#### F5 — 监控与可视化模块
- 实时DAG图：展示任务节点状态（颜色区分：待执行/执行中/完成/失败），支持手动调整DAG（增删节点、修改依赖关系）
- Agent活动面板：每个Agent当前任务、历史完成数
- 长文本生成进度条：显示当前处于哪个FSM阶段
- 执行日志流：实时滚动显示各Agent的输出内容
- 实时预览面板：章节完成即追加Markdown内容，用户可实时查看写作进度
- 手动干预工具栏：暂停执行、跳过节点、手动重试
- 最终结果展示：Markdown渲染+一键导出（PDF/DOCX）

### 2.2 用户交互入口

- **任务创建页**：输入任务描述 + 选择生成模式（技术报告 / 小说 / 自定义） + 选择研究深度（快速/标准/深入）
- **编排监控页**：实时DAG可视化 + Agent状态面板
- **Agent管理页**：注册/查看/删除Agent
- **历史任务页**：已完成任务列表，可查看历史生成文档
- **结果展示页**：Markdown渲染 + 导出

---

## 3. 非功能需求

| 指标 | 目标值 |
|------|--------|
| 并发任务数 | 支持至少5个并发任务 |
| 执行层Agent实例数 | 支持同时运行10个执行层Agent实例 |
| 任务分解准确率 | ≥80%（人工评估） |
| 长文本生成长度 | ≥10,000字 |
| Agent间消息延迟 | ≤100ms（Redis Streams） |
| 任务故障恢复时间 | ≤30秒 |
| 前端实时刷新 | ≤2秒延迟（WebSocket推送） |
| API响应时间 | 普通接口≤500ms |
| 系统可用性 | 本地Demo环境稳定运行 |

---

## 4. 非目标（不在本期实现范围）

- 不实现用户鉴权系统（单用户本地/局域网使用）
- 不实现Agent的自主学习/自我进化
- 不实现对比实验模块（已从需求中移除）
- 不支持移动端
- 不实现生产级别的高可用部署

---

## 5. 验收标准

1. 三层架构（编排/管理/执行）可正常运行，每层至少支持2个Agent实例
2. 输入一个任务主题，系统自动生成DAG并驱动Agent执行完成
3. 长文本生成场景（技术报告/小说）输出≥10,000字，结构完整
4. 前端DAG图实时更新，能清晰观察任务执行全过程
5. 最终文档可导出为DOCX/PDF格式

## 6. 参考仓库落地补充（2026-03-21）

参考仓库：`Imbad0202/academic-research-skills`（研究→写作→审查→修订全流程编排）。

### 6.1 新增功能需求（建议纳入 Step 4.3+）
1. 阶段门禁（Quality Gate）
   - 在审查前增加 `PRE_REVIEW_INTEGRITY` 关卡。
   - 在定稿前增加 `FINAL_INTEGRITY` 关卡。
   - 关卡失败时必须阻断进入下一阶段。
2. 复审闭环（Re-review Loop）
   - 增加 `RE_REVIEW` / `RE_REVISE` 子流程。
   - 每次修订都输出“问题-修改-证据”对照表。
3. 中途接入（Mid-entry）
   - 用户可从“已有初稿/已有评审意见”直接进入对应阶段。
   - 系统自动补齐必要前置步骤（如完整性校验）。

### 6.2 Prompt 参考要点（可直接复用思路）
1. 审查 Prompt 要求“反方挑战”段落（Devil’s Advocate），强制指出最强反例。
2. 审查输出统一 Rubric 评分（0-100）+ 维度分项，便于 FSM 决策。
3. 修订 Prompt 强制输出 `issue -> action -> evidence` 三列映射，避免“口头修订”。
4. 完整性校验 Prompt 要求逐条 claim 校验状态：`verified / weak / unverifiable`。

### 6.3 技能注入参考要点
1. 将“流程编排能力”和“写作能力”解耦：
   - Orchestrator 只做阶段检测、门禁判定、流转，不直接产出正文。
   - Writer/Reviewer/Consistency 负责具体内容。
2. 引入“阶段化技能注入”：
   - 阶段前注入 `research/outline/writing/review/revision` 对应技能片段。
   - 避免一次性注入全部技能导致上下文污染。
3. 注入优先级：
   - `system baseline` < `role system` < `stage skill` < `task-specific constraints`。
4. 验收新增：每轮修订必须产出“问题闭环率”指标（目标 >= 95%）。

## 2026-03-21 Implementation Addendum — Agent Retry/Fallback Controls
- New runtime contract: task-level `agent_config` can override retry and fallback behavior.
- Required fields:
  - `max_retries`: bounded integer, consumed by runtime LLM call path.
  - `fallback_models`: ordered model candidates for degradation path.
- Product expectation: when primary model fails, system retries then degrades according to override chain before failing task node.
