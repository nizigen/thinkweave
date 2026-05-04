## Actionable Output Contract
当章节标题或任务语义包含 implementation/how-to/步骤/路径/建议 时，正文必须产出下列可执行结构：

1. `ACTIONABLE_CHECKLIST`
- 至少 5 条可执行步骤。
- 每条包含 owner、input、output、done_criteria。

2. `DECISION_MATRIX`
- 至少 3 个备选方案。
- 每个方案包含 benefit、cost、risk、trigger_condition。

3. `TIMELINE_ESTIMATE`
- 至少 3 个阶段（start/end 或 duration）。
- 标注关键依赖和阻塞条件。

4. `RISK_ASSESSMENT`
- 至少 4 条风险，包含 impact、likelihood、mitigation、fallback。

若信息不足，必须在 `missing_evidence_items` 中明确记录，不得用空话替代。
