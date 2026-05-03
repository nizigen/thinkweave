# ThinkWeave REQUIREMENTS

## R1 Stage Contracts
- Define semantic stage contracts and role mapping.
- Inject `stage_code`, `schema_version`, `stage_contract` into DAG payloads.

## R2 Pipeline Rewrite
- Implement research-first flow:
  Research -> Outline -> Section Writer -> Reviewer -> Consistency.

## R3 Repair And Quality
- Add targeted repair DAG from consistency failures.
- Add final polish and quality gates for structure/evidence/length/conflicts.

## R4 Observability
- Keep monitor behavior aligned with new stage semantics.
- Expose failure reasons, retry traces, repair waves.

## R5 Runtime State Correctness
- Introduce a single coordination boundary for task, FSM, node, and Agent state updates.
- Add optimistic locking and transition audit logs.
- Make checkpoints sufficient for mid-task resume.

## R6 Recoverable Memory And Resource Control
- Persist SessionMemory dedup and topic territory state across Agent restarts.
- Isolate cognee behind a memory adapter with fallback behavior.
- Enforce Writer concurrency, token, and request budgets.

## R7 Event-Driven Coordination And Realtime Feedback
- Replace scheduler and monitor polling hot paths with Redis Stream event consumption where safe.
- Define realtime message envelopes for progress, previews, review scores, fact-check results, errors, and Agent health.
- Support replay/ACK behavior for high-priority realtime messages.

## R8 Enforced Output Quality Gates
- Require a single core thesis and bounded primary outline before writing.
- Require claim-evidence binding for market, business, and technical claims.
- Add reviewer scoring for evidence sufficiency, specificity, and source attribution.

## R9 Fact Check, Specificity, And Actionability
- Add FACT_CHECK state and FactCheckAgent for technical claim validation.
- Require quantified boundaries for scenarios, counterexamples, and constraints.
- Decompose implementation sections into actionable checklist, matrix, timeline, and risk outputs.
- Route unapplied consistency recommendations back into targeted rewrites.
