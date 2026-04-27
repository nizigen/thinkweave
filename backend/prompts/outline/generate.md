你将为长文任务生成“章节结构 + 研究协议”。

## 写作语言总则
- 默认正文语言：简体中文。
- 非必要不用英文整句；仅在术语、标准名、专有名词、引用题名中允许英文。
- 若用户明确要求英文，再切换主语言。

## 输入
- title: {title}
- mode: {mode}
- target_words: {target_words}
- draft_text: {draft_text}
- review_comments: {review_comments}
- style_requirements: {style_requirements}
- source_policy: {source_policy}
- research_keywords: {research_keywords}

## 输出格式（Markdown）
按以下 4 个区块输出：

### 1) Topic Anchor
- 定义本报告“要回答的问题”和“非目标范围（non-goals）”。

### 2) Chapter Plan
按章节列出：
- chapter title
- chapter summary（80-180字，中文）
- key points（3-6条）
- context bridges（前章->本章->后章）
- owns（本章负责）
- boundary（本章不覆盖）
- evidence needs（证据类型）

### 3) research_protocol（JSON）
必须给出 fenced JSON，字段至少包含：
- theme_definition
- keyword_buckets.core_terms / expansion_terms / exclusion_terms
- source_allowlist.preferred_domains / allowed_source_types / forbidden
- query_blueprint（按 chapter_index 给查询）

### 4) topic_claims（JSON）
必须给出 machine-readable 的 topic_claims，字段至少包含：
- chapter_index
- owns
- boundary
- assigned_evidence

## 质量要求
- 明确边界，避免章节重叠。
- 研究协议必须可执行，避免泛化空话。
- 结构需覆盖“背景、现状、分析或方法、结论/展望”。
- 标题层级最多二级：仅允许 `#` 与 `##`（或编号 `1` / `1.1`），禁止三级标题（如 `###` 或 `1.1.1`）。
- 章节标题与摘要默认使用中文，避免中英混杂导致术语漂移。
