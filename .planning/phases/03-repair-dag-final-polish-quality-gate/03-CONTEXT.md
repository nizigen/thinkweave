---
phase: "03"
name: "repair-dag-final-polish-quality-gate"
status: "discussed"
updated: "2026-04-26"
---

# Phase 3: Repair DAG + Final Polish + Quality Gate — Context

## Domain Boundary
Implement repair-loop behavior and final quality gates for the existing stage chain.

In scope:
- Consistency-failure repair DAG behavior
- Final polish and terminal quality gate policy
- Failure semantics and completion policy

Out of scope:
- New product capabilities outside repair/gate domain
- Web observability UI overhaul (belongs to Phase 4)

## Canonical Refs
- `backend/app/services/stage_contracts.py`
- `backend/app/services/dag_scheduler.py`
- `backend/app/services/long_text_fsm.py`
- `backend/prompts/orchestrator/decompose.md`
- `backend/prompts/writer/write_chapter.md`
- `backend/prompts/consistency/check.md`

## Decisions

### D1. Repair Trigger Policy (Locked)
Use the recommended hybrid policy:
- If consistency `pass=false`, inject targeted repair wave first.
- Keep max consistency repair waves at `2` (`MAX_CONSISTENCY_REPAIR_WAVES`).
- Keep per-node retry guard behavior; if still unresolved after retries/waves, defer to final gate decision path.

### D2. Repair Scope Policy (Locked)
Use chapter-targeted repair by default:
- Repair only targeted chapter writer/reviewer plus follow-up consistency node.
- Do not backtrack to researcher/outline in normal path.
- Global corrective expansion remains final-gate fallback, not primary repair path.

### D3. Final Quality Gate Strictness (Locked)
Use strict-but-operational gate profile:
- Keep target-word minimum ratio at `0.9` (`MIN_TARGET_WORD_RATIO`).
- Keep schema/evidence constraints enforced by stage contracts (KonrunsGPT-style stage semantics).
- Keep conflict/style/claim checks as hard gate inputs, with explicit failure reason surfaced.

### D4. Terminal Policy After Max Repair (Locked)
Use deterministic terminal semantics:
- Exhausted auto expansion waves (`AUTO_EXPANSION_MAX_WAVES=3`) or unresolved gate failure should end in explicit `failed` with reason.
- Avoid silent pass-through after exhausting repair budgets.
- Preserve explicit `blocking_reason`/failure transparency for downstream diagnostics.

## KonrunsGPT Alignment Notes
- Preserve stage semantics and role contract mapping from KonrunsGPT-inspired stage chain.
- Keep evidence-first writing and claim-traceability constraints in writer/reviewer/consistency prompts.
- Treat final gate as contract enforcement layer, not optional post-processing.

## Discretion Areas
- Prompt wording fine-tuning that does not change locked policies above.
- Exact error text phrasing as long as machine-readable failure reason remains stable.
- Minor threshold calibration only if it preserves D3 gate strictness profile.

## Deferred Ideas
- None captured in this discuss cycle.
