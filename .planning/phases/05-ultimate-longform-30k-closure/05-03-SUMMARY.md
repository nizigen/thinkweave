# 05-03 Summary: Assembly Editor + Hybrid Consistency + Repair Budget

## Completed

- Dedicated assembly editor stage integrated into scheduler:
  - Added pre-finalize insertion of a global writer node `全稿Assembly编辑收敛（术语统一/重复折叠/结论收敛）` when manuscript is ready for finalization.
  - Finalization now prefers assembly-editor output over naive chapter concatenation when present.
- Hybrid consistency checking contract upgraded:
  - Consistency prompt now uses `chapters_summary + key_fragments + full_text` hybrid review mode.
  - Output contract expanded with `severity_summary` and `repair_priority`.
- Repair budget manager implemented:
  - Added `consistency_repair_budget` ledger in checkpoint data with points, rounds, and event history.
  - Repair waves now consume dynamic budget by per-chapter issue severity weights.
  - Budget exhaustion produces structured `BUDGET_EXCEEDED` failure payload instead of opaque retries.
- Stage/prompt/runtime alignment:
  - Stage resolver recognizes assembly-editor titles as `ASSEMBLY` stage.
  - Writer prompt now includes `is_assembly_editor` discipline.
  - Worker consistency JSON validator now requires `severity_summary` + `repair_priority`.

## Files changed

- `backend/app/services/dag_scheduler.py`
- `backend/app/services/long_text_fsm.py`
- `backend/app/services/stage_contracts.py`
- `backend/app/agents/worker.py`
- `backend/prompts/consistency/check.md`
- `backend/prompts/writer/write_chapter.md`
- `backend/tests/test_dag_scheduler.py`
- `backend/tests/test_long_text_fsm.py`
- `backend/tests/test_agent_prompt_contracts.py`

## Verification

- `cd backend && .venv/bin/pytest -q tests/test_long_text_fsm.py tests/test_dag_scheduler.py -k "consistency or repair or finalize"`
  - Result: `19 passed`
- `cd backend && .venv/bin/pytest -q tests/test_agent_prompt_contracts.py`
  - Result: `5 passed`
- `cd backend && .venv/bin/pytest -q tests/test_specialized_agents.py -k "consistency"`
  - Result: `1 passed`

## Notes

- Existing warning output references an external venv path (`agentic-nexus`) in this environment; unrelated to this plan's changes.
