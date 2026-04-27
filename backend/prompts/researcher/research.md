你需要输出“章节可执行的研究方案与证据账本”。

## 输入
- task title: {title}
- mode: {mode}
- depth: {depth}
- target_words: {target_words}
- full_outline: {full_outline}
- source_policy: {source_policy}
- research_keywords: {research_keywords}
- evidence_pool_seeds: {evidence_pool_seeds}
- evidence_pool_summary: {evidence_pool_summary}
- evidence_pool_markdown: {evidence_pool_markdown}
- memory_context: {memory_context}

## 长文导向要求
1. 本任务优先保障长文本可写性，尤其 `target_words >= 30000` 的场景。
2. evidence_ledger 必须覆盖主要章节，不允许“证据集中在少数章节”。
3. 每条关键论断应有可追踪来源，无法追踪时必须显式标 uncertainty。
4. 查询策略要具备“定义、机制、比较、风险、实施、评估”六类覆盖。

## 输出（硬约束）
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
      "queries": ["中文检索词", "英文扩展词"]
    }}
  ],
  "evidence_ledger": [
    {{
      "evidence_id": "E1",
      "claim_target": "该证据支持的论断",
      "required_source_type": "standard|paper|dataset|official_report|industry_report|patent",
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

## 质量约束
1. keyword_plan 至少 6 个 bucket，每个 bucket 至少 2 条 queries。
2. 每个 bucket 至少包含 1 条中文 query 与 1 条英文扩展 query。
3. evidence_ledger 至少 12 条；当 `target_words >= 30000` 时至少 18 条；当 `target_words >= 50000` 时至少 28 条。
4. 每条 evidence 必须包含 `source_url/source_title/published_at`，三者缺一不可。
5. chapter_mapping 在 full_outline 非空时不得为空，且至少覆盖 80% 章节。
6. 优先复用 evidence_pool_markdown 中已有高价值证据，避免重复制造同类低质量条目。
7. 若 mode=report，优先 domain 白名单中的 OA / 专利 / 权威报告来源。
8. 若 mode=novel，仅把现实来源用于背景与设定约束，不得伪装为事实研究结论。

## 反模式（禁止）
- 输出空泛关键词（如“发展趋势”“应用价值”）但无检索可执行性。
- 大量来源无 URL 或无时间信息。
- 用同一来源支撑多个不相干核心结论。
- 把不确定信息写成确定事实，不进 uncertainty_flags。
