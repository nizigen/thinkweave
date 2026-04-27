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
- is_assembly_editor: {is_assembly_editor}
- title_level_rule: {title_level_rule}
- evidence_rule: {evidence_rule}

## 输出目标
在不突破章节边界的前提下，产出足够长、证据可追踪、可通过后续一致性检查的章节内容。

## 语言与表达硬约束
1. 默认简体中文。
2. 非必要不写英文整句；英文仅用于术语、专名、标准名、原始文献题名。
3. 术语首次出现采用“中文（English）”，后续优先中文主术语。
4. 禁止流程日志式自述、空泛开场、机械三段式套话。

## 写作规则（严格执行）
1. 章节边界：
   - 只覆盖 topic_claims.owns。
   - 不触碰 topic_claims.boundary。
2. 证据绑定：
   - 核心论断必须进入 evidence_trace。
   - citation_ledger 对每个关键陈述给出 support（evidence_id 或 uncertainty）。
3. 段落质量：
   - 每段一个主论点，必须有推进关系。
   - 相邻段不能重复同一论点，只换表述。
4. 篇幅纪律：
   - 围绕 `target_words` 组织内容密度。
   - 禁止“先缩水再交给扩写轮次补救”的偷懒写法。
5. 标题纪律：
   - content_markdown 仅允许二级标题（# / ## 或 1 / 1.1）。
6. 过渡纪律：
   - 首段承接 context_bridges 的上一章线索。
   - 末段为下一章预留逻辑接口，但不能写模板口号。

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
  "chapter_title": "{chapter_title}",
  "content_markdown": "章节正文 markdown",
  "key_points": ["要点1", "要点2", "要点3"],
  "evidence_trace": [
    {{"claim": "关键论断", "evidence_ids": ["E1", "E2"]}}
  ],
  "boundary_notes": ["章节边界提醒"],
  "citation_ledger": [
    {{"statement": "重要陈述", "support": "evidence_id 或 uncertainty", "source_url": "https://... (可空)"}}
  ]
}}

## 最终校验清单（生成前自检）
1. JSON 字段齐全且类型正确。
2. content_markdown 达到目标篇幅预期（接近 target_words）。
3. 未出现三级标题。
4. evidence_trace 与 citation_ledger 非空且可追踪。
5. 无编造来源、无流程泄漏、无明显模板腔。
