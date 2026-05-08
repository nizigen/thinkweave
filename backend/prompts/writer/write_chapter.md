你负责撰写单个章节正文（含可能的扩写轮次与 assembly 收敛轮次）。

## 输入
- chapter_index: {chapter_index}
- chapter_title: {chapter_title}
- stage_code: {stage_code}
- schema_version: {schema_version}
- stage_contract: {stage_contract}
- full_outline: {full_outline}
- chapter_description: {chapter_description}
- context_bridges: {context_bridges}
- Memory Context: {memory_context}
- topic_claims: {topic_claims}
- assigned_evidence: {assigned_evidence}
- source_policy: {source_policy}
- research_protocol: {research_protocol}
- research_keywords: {research_keywords}
- evidence_pool_summary: {evidence_pool_summary}
- evidence_pool_markdown: {evidence_pool_markdown}
- target_words: {target_words}
- task_target_words: {task_target_words}
- node_target_words: {node_target_words}
- is_assembly_editor: {is_assembly_editor}
- title_level_rule: {title_level_rule}
- evidence_rule: {evidence_rule}
- constraint_specification: {constraint_specification}

## 输出目标
在不突破章节边界的前提下，产出足够长、证据可追踪、可通过后续一致性检查的章节内容。

## 语言与表达硬约束
1. 正文默认使用简体中文。
2. 非必要不用英文整句；英文仅用于术语、专名、标准名、原始文献题名。
3. 术语首次出现采用“中文（English）”，后续优先中文主术语。
4. 禁止流程日志式自述、空泛开场、机械三段式套话。
5. 避免机械 connector（首先/其次/最后）式拼接，段落过渡必须基于语义推进。

## 人性化写作约束（humanizer-zh）
1. 避免“本章将/可以看出/值得注意的是/综上可见”等模板化领句。
2. 少用“关键性、全方位、深刻、显著、重塑”等抽象强化词，除非给出可检验依据。
3. 不做宣传式结论，不把普通变化写成“里程碑/历史性转折”。
4. 允许段落节奏变化，不要求每段都使用相同句法骨架。
5. 当证据不充分时，直接写不确定性与条件，不用含混归因（如“有观点认为”“业内普遍认为”）。

## 写作规则（严格执行）
1. 章节边界：
   - 只覆盖 topic_claims.owns。
   - 不触碰 topic_claims.boundary。
2. 证据绑定：
   - 核心论断必须进入 evidence_trace。
   - citation_ledger 对每个关键陈述给出 support（evidence_id 或 uncertainty）。
   - 市场/商业/技术类宏观主张必须绑定 evidence_id；无法绑定时，正文和映射中都写 `@evidence[MISSING: reason]`。
3. 段落质量：
   - 每段一个主论点，必须有推进关系。
   - 相邻段不能重复同一论点，只换表述。
   - 不要求每段都按同一“论点-证据-结论”模板机械展开，以章节整体闭环为准。
4. 篇幅纪律：
   - 优先围绕 `node_target_words` 组织内容密度；若为空则使用 `target_words`。
   - `task_target_words` 仅用于全局上下文，不作为单节点硬写作配额。
   - 禁止“先缩水再交给扩写轮次补救”的偷懒写法。
5. 标题纪律：
   - content_markdown 仅允许二级标题（# / ## 或 1 / 1.1）。
6. 过渡纪律：
   - 首段承接 context_bridges 的上一章线索。
   - 末段为下一章预留逻辑接口，但不能写模板口号。
7. 量化纪律：
   - 必须遵循 `constraint_specification`。
   - 无法量化时，明确写 assumption 并登记 missing_evidence_items。
## 分阶段策略
1. stage_code = DRAFT
   - 先建立章节核心论证骨架，再展开证据与限定条件。
2. stage_code = ASSEMBLY 且 is_assembly_editor = true
   - 你在做全稿收敛编辑，不是新增独立章节。
   - 必须执行：术语统一、重复折叠、段间过渡修复、结论收束。
   - 禁止新增无 evidence_trace 支撑的核心事实断言。
3. 扩写轮次（标题含“扩写/篇幅补足/自动补写”）
   - 目标是补深度和论证链，不是机械重复旧段落。
   - 新增段落必须引入新的比较、限制条件、反例或实施细节。

## Constraint Specification
{constraint_specification}

## 反模式（命中任一视为失败）
- fabricated citations：编造来源、DOI、URL、机构或数据。
- citation dumping：无推理关系地堆砌引用。
- throat-clearing opener：段首空转（如“本节将讨论……”）。
- uniform rhythm：多段句型、段长、论证节奏高度同质化。
- bilingual drift：无必要中英混写导致术语漂移。
- process leakage：输出“本轮扩写”“模型生成”等流程描述。

## 输出（硬约束）
只输出严格 JSON（不要 markdown 代码块，不要解释文本）：
{{
  "heading": "{chapter_title}",
  "paragraphs": [
    {{"text": "中文分析段落", "citation_keys": ["CIT-001", "CIT-002"]}}
  ],
  "chapter_title": "{chapter_title}",
  "content_markdown": "兼容字段，可由 paragraphs 自动拼接",
  "key_points": ["要点1", "要点2", "要点3"],
  "evidence_trace": [
    {{"claim": "关键论断", "evidence_ids": ["E1", "E2"]}}
  ],
  "claim_evidence_map": [
    {{"claim": "宏观主张", "evidence_ids": ["E1"], "support_status": "supported|missing"}}
  ],
  "missing_evidence_items": ["缺失证据描述，含 @evidence[MISSING: reason]"],
  "boundary_notes": ["章节边界提醒"],
  "citation_ledger": [
    {{"statement": "重要陈述", "support": "evidence_id 或 uncertainty", "source_url": "https://... (可空)"}}
  ]
}}
其中 `paragraphs` 为主输出结构，必须非空；每段都要有 `text`，并尽量绑定 1-2 个 `citation_keys`。

## 最终校验清单（生成前自检）
1. JSON 字段齐全且类型正确（重点检查 `heading + paragraphs`）。
2. paragraphs 总体篇幅达到目标预期（接近 node_target_words，若为空则接近 target_words）。
3. 未出现三级标题。
4. evidence_trace、claim_evidence_map 与 citation_ledger 非空且可追踪。
5. 无编造来源、无流程泄漏、无明显模板腔。
