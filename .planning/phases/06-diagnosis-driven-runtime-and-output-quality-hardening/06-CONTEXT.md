---
phase: "06"
name: "diagnosis-driven-runtime-and-output-quality-hardening"
status: "discussed"
updated: "2026-05-03"
source_docs:
  - docs/ARCHITECTURE_DIAGNOSIS.md
  - docs/SYSTEM_DIAGNOSIS.md
---

# Phase 6: Diagnosis-Driven Runtime And Output Quality Hardening - Context

## Domain Boundary

This phase converts the two May 3 diagnosis reports into executable hardening work. The scope is not a new product feature; it is a reliability and output-quality correction pass over the existing longform agent pipeline.

In scope:
- Runtime correctness: state consistency, optimistic locking, retry ownership, checkpoint completeness, recovery paths.
- Scheduler and coordination: event-driven Redis Stream flow, Agent health checks, WriterPool limits, FlowController separation.
- Memory and evidence: SessionMemory persistence, cognee isolation, Evidence Pool readiness, RAG input validation.
- Output quality gates: premise focus, evidence-backed claims, quantified constraints, actionable implementation sections.
- User/operator feedback: realtime event protocol, chapter preview, detailed errors, audit logs, manual intervention APIs.

Out of scope:
- Replacing Redis Streams with Pub/Sub or external queues.
- Introducing LangChain, LlamaIndex, Celery, socket.io, or direct `openai` imports.
- Rewriting the frontend design system unrelated to generation observability.
- Removing pgvector RAG; pgvector remains for RAG while cognee remains behind memory adapters.

## Problem Synthesis

### P0 Stability Problems
- `task.status`, `task.fsm_state`, `task_node.status`, and Redis Agent state can diverge, causing zombie tasks and unreliable resume.
- `TaskNode` updates lack optimistic locking, so concurrent Agent writes can overwrite each other.
- Retry policy is split across DAG Scheduler and FSM, making terminal failure routing ambiguous.
- SessionMemory loses dedup and topic territory data on process restart.
- Writer concurrency is not tied to LLM token/request budgets.

### P0 Output Quality Problems
- Outline generation lacks a single core-thesis constraint, allowing broad parallel chapter sets.
- Evidence Pool and Writer contracts allow unsupported market/business claims.
- Reviewer does not score evidence sufficiency, specificity, or source attribution.

### P1 Reliability And Quality Problems
- DAG scheduling and realtime updates still rely on polling instead of completion/state events.
- FSM and DAG coordination is coupled; FlowController responsibility is implicit.
- Writer prompts allow vague qualifiers instead of quantified boundary conditions.
- Implementation sections are generated as strategy prose rather than checklists, matrices, estimates, and risks.

### P2 Operator Experience Problems
- Checkpoint data is too shallow to restore FSM path, node state, memory snapshot, and Agent context.
- State transitions are not auditable.
- Manual force-transition and skip-node operations are missing.
- WebSocket messages lack ACK/replay semantics, rich message types, previews, and detailed error envelopes.

## Locked Decisions

### D1. Preserve Existing Architectural Constraints
All implementation must preserve the AGENTS.md constraints: Redis Streams only, no Pub/Sub, no Celery, no LangChain/LlamaIndex, no direct `openai` import, prompts loaded from `backend/app/prompts`.

### D2. StateStore Becomes The Coordination Boundary
Runtime state updates must be mediated through a StateStore-style service so FSM transitions, node updates, audit logs, and Redis events are emitted consistently.

### D3. Retry Ownership Must Be Explicit
DAG handles transient node execution retries with backoff. FSM handles semantic quality loops such as review, consistency, and premise failures. Terminal failure routing must be centralized.

### D4. SessionMemory Must Be Recoverable
Session dedup, topic territory, and relevant memory snapshots must have a Redis-backed persistence path while retaining `MEMORY_ENABLED=false` fallback behavior.

### D5. Quality Gates Must Be Enforceable, Not Advisory
Premise, evidence, specificity, and actionability requirements must be encoded in prompts, schemas, reviewer dimensions, FSM routing, and tests.

### D6. Event Streams Are The User And Operator Contract
Scheduler, FSM, Agent health, realtime UI, and audit surfaces should consume Redis Stream events instead of polling whenever possible.

## Canonical References

### Diagnosis Inputs
- `docs/ARCHITECTURE_DIAGNOSIS.md` — 5-dimensional diagnosis for execution flow, data flow, Agent collaboration, state management, realtime feedback.
- `docs/SYSTEM_DIAGNOSIS.md` — article-defect reverse diagnosis mapping output-quality defects to code-level gaps.

### Runtime Coordination
- `backend/app/services/long_text_fsm.py` — FSM states, semantic loops, checkpoint/resume behavior.
- `backend/app/services/dag_scheduler.py` — node scheduling, retries, timeout handling, Redis dispatch.
- `backend/app/services/task_service.py` — task API persistence and status views.
- `backend/app/models/task.py` and `backend/app/models/task_node.py` — task/node state schema and migration targets.

### Agent And Memory Layer
- `backend/app/agents/base_agent.py` — Redis consumer loop and middleware pipeline.
- `backend/app/agents/worker.py` — role execution and LLM/prompt path.
- `backend/app/agents/reviewer_agent.py` — quality dimensions and review results.
- `backend/app/agents/consistency_agent.py` — cross-chapter consistency checks and repair routing.
- `backend/app/memory/session.py` — SessionMemory API and persistence target.
- `backend/app/memory/knowledge/graph.py` — KnowledgeGraph/cognee adapter target.

### Prompt And Quality Contracts
- `backend/app/prompts/outline/main.md` or active outline prompt path — premise/thesis gate contract.
- `backend/app/prompts/writer/*.md` — evidence, specificity, and actionability requirements.
- `backend/app/prompts/reviewer/*.md` — evidence and specificity scoring requirements.
- `backend/app/prompts/consistency/*.md` — cross-chapter and self-application feedback checks.

### Realtime And Observability
- `backend/app/main.py` and WebSocket routes — task realtime event stream integration.
- `frontend` task monitor views — rendering target for message protocol, preview, and errors.
- `docs/progress.md` and `docs/task_plan.md` — documentation update targets.

## Deferred Ideas

- Full multi-tenant quota/billing controls; this phase adds runtime budgets, not billing.
- Graph memory replacement; this phase isolates cognee but does not remove it.
- Complete admin console redesign; this phase adds backend operations endpoints and minimal frontend visibility only where necessary.
