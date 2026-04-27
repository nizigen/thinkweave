你需要输出“章节可执行的研究方案与证据账本”。

## 输入
- task title: {title}
- mode: {mode}
- target_words: {target_words}
- full_outline: {full_outline}
- source_policy: {source_policy}
- research_keywords: {research_keywords}
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
      "priority": "high|medium|low"
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
- evidence_ledger 至少 8 条。
- full_outline 不为空时，chapter_mapping 不得为空。
- 查询必须与主题直接相关，禁止离题扩散。
- 严格遵守 source policy。
