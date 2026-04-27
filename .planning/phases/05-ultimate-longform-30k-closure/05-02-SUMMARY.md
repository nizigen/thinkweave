# 05-02 Summary: 30k-aware planning + node budget ledger

## Completed

- Implemented target-word-aware chapter minimums in decomposer:
  - Added 30k/50k thresholds that raise minimum primary chapter count by depth profile.
  - Applied guard in both normal LLM decomposition path and fallback DAG path.
- Implemented per-node budget envelope in scheduler assignment payload:
  - Added `planned_words`, `word_floor`, `word_ceiling`.
  - Writer budgets now derive from task target, chapter shape, and expansion status.
- Implemented node budget ledger persistence in checkpoint:
  - Added `checkpoint_data.node_budget_ledger[node_id]` with stage/role/title and budget envelope.
  - Writer length gate now prefers ledger `word_floor` before heuristic fallback.
- Upgraded auto-expansion policy to adaptive strategy:
  - Decision based on remaining gap, waves-left risk score, and cost cap.
  - Added structured `checkpoint_data.expansion_decisions[]` for explainability.

## Files changed

- `backend/app/services/task_decomposer.py`
- `backend/app/services/dag_scheduler.py`
- `backend/tests/test_task_decomposer.py`
- `backend/tests/test_dag_scheduler.py`

## Verification

- `cd backend && .venv/bin/pytest -q tests/test_task_decomposer.py tests/test_dag_scheduler.py`
  - Result: `92 passed`
- `cd backend && .venv/bin/pytest -q tests/test_e2e_flows.py -k "target_words or expansion or long"`
  - Result: no matching tests (`15 deselected`), command executed successfully with no selected cases.

## Notes

- Existing warning noise references an external venv path (`agentic-nexus`) in this environment; unrelated to this plan’s code changes.
