你将为长文任务生成“章节结构 + 研究协议 + 长度预算”。

## 输入
- title: {title}
- mode: {mode}
- depth: {depth}
- target_words: {target_words}
- draft_text: {draft_text}
- review_comments: {review_comments}
- style_requirements: {style_requirements}
- source_policy: {source_policy}
- research_keywords: {research_keywords}
- evidence_pool_summary: {evidence_pool_summary}
- evidence_pool_markdown: {evidence_pool_markdown}

## 语言与风格硬约束
1. 默认简体中文。
2. 非必要不写英文整句；英文只用于术语/标准名/专有名词。
3. 章节命名避免口号式空话，要能直接指导 writer 落地。

## 任务要求（重点保证长文可达）
1. 必须先定义唯一核心论点（core_thesis），全篇所有主章节都服务于该论点。
2. 输出必须体现清晰论证主线：问题界定 -> 证据展开 -> 机制/方法 -> 落地/风险 -> 结论。
3. 每章必须提供 owns/boundary，避免跨章重复。
4. 每章必须声明 evidence_needs，避免后续“无证据硬写”。
5. 严禁生成 6-8 个平行一级章节但没有主线归属说明。
6. primary chapters 默认不超过 3 个；超过时必须给出必要性说明并放入 optional chapters。
7. 若 `target_words >= 30000`，章节计划必须显式给出：
   - 主章节数量建议（至少 9 章）；
   - 每章建议字数区间；
   - 预留扩写章节或扩写轮次说明。
8. 若 `target_words >= 50000`，需给出分层扩写策略（主章节 + 补写层 + 收敛层）。

## 输出格式（Markdown，必须包含以下区块）
### 1) Topic Anchor
- 用 3-6 条要点定义：
  - 研究核心问题（必须回答）
  - 非目标范围（明确不写）
  - 全篇主论点（可辩护、可被证据检验）

### 2) Length Budget Plan
- 给出总字数预算拆分：
  - total_target_words
  - baseline_chapter_count
  - per_chapter_budget（按章）
  - expansion_reserve（预留补写字数）
- 预算必须与 target_words 对齐，不得明显低估。

### 3) Chapter Plan
按章节输出，建议使用 `第N章：标题`。必须区分 primary chapters 和 optional chapters：
- chapter_title
- chapter_summary（120-220字）
- key_questions（2-4条）
- key_points（4-7条）
- context_bridges（上一章如何进入本章，本章如何引到下一章）
- owns（本章必须覆盖）
- boundary（本章禁止覆盖）
- evidence_needs（source type + why）
- thesis_contribution（本章如何支撑 core_thesis）
- suggested_word_budget（整数）

### 4) research_protocol（JSON fenced code）
必须输出 ```json 代码块，至少包含：
{{
  "theme_definition": "...",
  "keyword_buckets": {{
    "core_terms": [],
    "expansion_terms": [],
    "exclusion_terms": []
  }},
  "source_allowlist": {{
    "preferred_domains": [],
    "allowed_source_types": [],
    "forbidden": []
  }},
  "query_blueprint": [
    {{
      "chapter_index": 1,
      "queries": ["中文主检索词", "英文扩展词"]
    }}
  ]
}}

### 5) topic_claims（JSON fenced code）
必须输出 ```json 代码块，至少包含：
{{
  "claims": [
    {{
      "chapter_index": 1,
      "owns": [],
      "boundary": [],
      "assigned_evidence": []
    }}
  ]
}}

### 6) outline_contract（JSON fenced code，PREMISE_GATE 直接消费）
必须输出 ```json 代码块，至少包含：
{{
  "core_thesis": "一句可证伪、可验证的核心论点",
  "primary_chapters": [
    {{
      "chapter_index": 1,
      "chapter_title": "第1章：...",
      "thesis_contribution": "本章对核心论点的贡献"
    }}
  ],
  "optional_chapters": [
    {{
      "chapter_title": "可选章节标题",
      "why_optional": "为什么可选"
    }}
  ],
  "acceptance_checklist": [
    "是否仅有一个 core_thesis",
    "primary_chapters 是否 <= 3",
    "每个 primary chapter 是否有 thesis_contribution"
  ]
}}

## 质量门槛
- 标题层级最多二级（仅 `#`/`##` 或 `1`/`1.1`）。
- 不得出现 `###` 或 `1.1.1`。
- 不得编造来源、统计数字、机构结论。
- 不得输出与章节无关的流程自述或模型自述。
