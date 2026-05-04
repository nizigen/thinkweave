---
phase: "06"
name: "diagnosis-driven-runtime-and-output-quality-hardening"
status: "research-complete"
updated: "2026-05-03"
---

# Phase 6 Research: Diagnosis-Driven Runtime And Output Quality Hardening

## Research Question

What must be planned so ThinkWeave can convert the May 3 architecture and system diagnosis into safe, testable implementation work without violating project constraints?

## Source Inputs

- `docs/ARCHITECTURE_DIAGNOSIS.md`
- `docs/SYSTEM_DIAGNOSIS.md`
- Existing GSD roadmap through Phase 5
- Project constraints from `AGENTS.md`

## Key Findings

### 1. Runtime Stability Is The First Bottleneck
The architecture diagnosis identifies multiple independent state writers: FSM, DAG Scheduler, task/node persistence, Redis Agent state, WebSocket monitor. This makes downstream improvements unsafe unless state mutation and event emission are centralized.

Planning implication:
- Start with StateStore, optimistic locks, retry ownership, transition audit, and checkpoint schema.
- Do not begin large event-driven or quality-loop rewrites until state mutation contracts exist.

### 2. Memory Persistence Is Required For Longform Resume
SessionMemory currently acts as a current-task dedup and territory map, but the diagnosis calls out restart loss. For 30k generation, losing dedup state can directly reintroduce repeated content and inconsistent chapter ownership.

Planning implication:
- Add Redis Hash persistence under task-scoped keys.
- Preserve in-memory fast path and `MEMORY_ENABLED=false` fallback.
- Include restore tests that simulate process restart.

### 3. Scheduler Realtime Work Should Follow StateStore
Moving from polling to Redis Stream event handling is high leverage, but unsafe if event payloads are emitted from many unrelated sites. StateStore and RealtimeEventPublisher should define the shared envelope first.

Planning implication:
- Build event envelopes and audit logs before replacing scheduler loops.
- Keep compatibility fallback to polling until event-driven path passes E2E.

### 4. Output Quality Problems Are Contract Problems
The system diagnosis maps article defects to weak contracts: outline lacks thesis constraints, writers can make unsupported claims, reviewers do not score evidence/specificity, and consistency does not feed recommendations back into rewriting.

Planning implication:
- Fix prompts and schemas together.
- Add Reviewer dimensions and FSM gates so prompt instructions are enforceable.
- Validate with generated OPC UA regression fixtures rather than only unit tests.

### 5. Actionability Requires Different Decomposition
Implementation sections are poor when treated as generic chapter prose. They need structured sub-nodes: checklist, decision matrix, timeline estimate, risk assessment.

Planning implication:
- Teach `task_decomposer` or stage-contract generation to split implementation chapters into actionability node types.
- Add prompt fragments for actionable sections and reviewer checks.

## Recommended Phase Shape

Wave 1: Stabilize runtime truth before broad refactor.
- Plan 06-01: StateStore, optimistic locking, retry ownership, checkpoint/audit.
- Plan 06-02: SessionMemory persistence, cognee isolation, WriterPool budgets, RAG validation.

Wave 2: Enforce output-quality contracts.
- Plan 06-03: Premise Gate, outline/writer evidence contracts, reviewer evidence dimensions.
- Plan 06-04: specificity constraints, implementation actionability, consistency feedback loop.

Wave 3: Event-driven observability and recovery.
- Plan 06-05: FlowController, event-driven scheduler/realtime protocol, Agent health, manual intervention APIs, E2E validation.

## Validation Architecture

### Unit Tests
- StateStore transition legality, atomic status update, event emission, audit log creation.
- Optimistic lock conflict behavior for TaskNode updates.
- Retry policy classification and backoff calculation.
- SessionMemory Redis persistence and restore.
- RAG query validation and fallback behavior.
- Reviewer scoring dimensions for evidence, specificity, and source attribution.

### Integration Tests
- FSM transition emits state event and audit log exactly once.
- DAG node completion event triggers ready-node scheduling without waiting for polling fallback.
- WriterPool throttles by concurrent writers and token estimates.
- WebSocket consumes Redis Stream realtime events and can replay missed messages from last ID.
- Manual skip-node recomputes ready nodes and records audit metadata.

### E2E Regression
- Generate an OPC UA report fixture and assert:
  - single core thesis present,
  - primary outline chapters are bounded,
  - market/business claims are evidence-bound,
  - technical OPC UA claims use evidence binding and reviewer/consistency routing,
  - implementation sections include checklist, matrix, estimate, and risk block,
  - realtime stream exposes preview, review score, consistency, and error messages.

### Safety Constraints
- Tests must use MockLLMClient and fakeredis.
- No external API calls in tests.
- No direct `import openai`.
- No Redis Pub/Sub.

## Risks

| Risk | Mitigation |
|------|------------|
| StateStore refactor touches high-risk runtime paths | Keep compatibility adapters and migrate one mutation path at a time |
| Event-driven scheduler changes race with old polling path | Run dual-path with feature flag, then remove polling after tests pass |
| Quality gates over-constrain generation | Gate thresholds configurable and surfaced in review output |
| Redis persistence introduces stale memory | Include version/hash on snapshots and clear task-scoped keys on task deletion |

## RESEARCH COMPLETE
