---
phase: 05-ultimate-longform-30k-closure
plan: "01"
status: completed
executed_at: "2026-04-27"
---

# Phase 5 Plan 01 Summary

## Delivered
- Researcher role now supports tool-backed execution path via `chat_with_tools` loop when runtime MCP tools are available; automatically falls back to chat-only path when unavailable.
- Structured researcher output contract hardened to require:
  - `topic_anchor/source_scope/keyword_plan/evidence_ledger/chapter_mapping/uncertainty_flags`
  - evidence entries include `source_url/source_title/published_at`.
- Prompt contracts updated to align evidence and citation fields across researcher/writer/reviewer.
- Task detail observability now includes:
  - `evidence_summary`
  - `citation_summary`
  derived from researcher + writer node outputs.

## Files Changed
- `backend/app/agents/worker.py`
- `backend/app/services/task_service.py`
- `backend/app/schemas/task.py`
- `backend/prompts/researcher/research.md`
- `backend/prompts/writer/write_chapter.md`
- `backend/prompts/reviewer/review_chapter.md`
- `backend/tests/test_specialized_agents.py`
- `backend/tests/test_agent_prompt_contracts.py`
- `backend/tests/test_e2e_flows.py`

## Verification Evidence
- `cd backend && .venv/bin/pytest -q tests/test_specialized_agents.py tests/test_agent_prompt_contracts.py tests/test_e2e_flows.py`
  - Result: `26 passed`
- `cd backend && .venv/bin/pytest -q tests/test_task_api.py tests/test_task_service_entry_stage.py`
  - Result: `49 passed`

## Notes
- Tool-backed path depends on runtime MCP client availability. If no MCP tools are connected, researcher path degrades gracefully to chat.
- This closes Plan 05-01 and unblocks 05-02 (30k-aware planning and adaptive budget).
