你需要输出“章节可执行的研究方案与证据账本”。

## 语言策略
- 输出说明与论断默认使用简体中文。
- 检索词可中英混合，但必须“中文主检索词 + 英文同义词扩展”并行设计。
- 非必要不使用英文整句描述分析结论。

## 输入
- task title: {title}
- mode: {mode}
- target_words: {target_words}
- full_outline: {full_outline}
- source_policy: {source_policy}
- research_keywords: {research_keywords}
- evidence_pool_seeds: {evidence_pool_seeds}
- evidence_pool_summary: {evidence_pool_summary}
- evidence_pool_markdown: {evidence_pool_markdown}
- memory_context: {memory_context}

## 输出
只输出严格 JSON（不要 markdown 代码块）：
{{
  "topic_anchor": "一句话定义研究锚点",
  "source_scope": {{
    "allowed": ["..."],
    "disallowed": ["..."],
    "time_window": "..."
  }},
  "keyword_plan": [
    {{
      "bucket": "definition|benchmark|method|risk|regulation|trend",
      "queries": ["q1", "q2", "q3"]
    }}
  ],
  "evidence_ledger": [
    {{
      "evidence_id": "E1",
      "claim_target": "该证据支持的论断",
      "required_source_type": "standard|paper|dataset|official_report",
      "priority": "high|medium|low",
      "source_url": "https://...",
      "source_title": "来源标题",
      "published_at": "YYYY-MM-DD"
    }}
  ],
  "chapter_mapping": [
    {{
      "chapter_hint": "章节标题或提示",
      "must_have_evidence_ids": ["E1", "E2"],
      "boundary_notes": ["边界说明"]
    }}
  ],
  "uncertainty_flags": ["需要人工确认的风险点"]
}}

## 研究质量要求
- keyword_plan 至少 4 个 bucket。
- 每个 bucket 至少包含 1 条中文 query。
- evidence_ledger 至少 8 条。
- evidence_ledger 中每条都必须包含 `source_url/source_title/published_at`。
- 优先从 evidence_pool_seeds 指定的 OA / 专利入口域名中选择候选来源。
- 当 mode=report 时，优先使用 industry_report_urls + oa_urls + patent_urls。
- 当 mode=novel 时，优先使用 fiction_reference_urls（世界观/叙事/文体参考），并避免伪造事实来源。
- 若 evidence_pool_markdown 已有可用条目，优先复用并补齐缺失字段，不要重复制造同类证据。
- full_outline 不为空时，chapter_mapping 不得为空。
- 查询必须与主题直接相关，禁止离题扩散。
- 严格遵守 source policy。
