## External Reference Alignment

This design is aligned with useful patterns from `C:/GitHub/Aletheia/docs/IMPLEMENTATION_PLAN.md`:
- phased memory rollout,
- lifecycle-bound runtime hooks,
- SessionMemory contract before Knowledge promotion.

This design explicitly does not inherit provider assumptions from external plans; this repository remains pinned to verified local runtime behavior.
# Cognee Memory Completion Design

**Scope:** Complete Step `4.1 + 4.1a + 4.1b` to production-ready quality by replacing the current "cognee-compatible/no-op" memory path with a real `cognee` integration, then wiring startup, runtime lifecycle, and verification so later Step `4.3/4.4` work has a stable base.

**Status:** Approved in-session on 2026-03-22

---

## Stage Gates

This lane is strictly governed by the tri-plugin process and cannot skip stages.

1. **Stage 1: planning**
   - approved design spec;
   - executable implementation plan;
   - both documents reviewed for process compliance.
2. **Stage 2: implementation**
   - every task must run in `RED -> GREEN -> REFACTOR` order;
   - broad runtime wiring is blocked until a real enabled-mode `cognee` integration probe passes.
3. **Stage 3: review and verification**
   - code review;
   - security review;
   - verification-before-completion with runnable startup/sub-flow evidence.

Any completion claim before Stage 3 passes is invalid.

## Problem

The current memory implementation is not complete by the standard required for this project:

- `backend/app/memory/adapter.py` is a light wrapper around hypothetical `cognee` calls with graceful no-op fallback.
- `backend/app/memory/session.py` exposes a minimal session API, but it does not yet prove real `cognee` backend behavior.
- Documentation/history currently treats parts of `4.1/4.1a/4.1b` as complete or partially complete, but the user clarified that this does not count as actual completion.
- The project goal now explicitly requires direct `cognee` usage, not a downgraded self-built substitute.

This creates three concrete risks:

1. Runtime memory behavior may silently degrade to no-op without detection.
2. Long-text lifecycle hooks cannot be trusted if storage is not real.
3. Later work on quality gates and knowledge promotion would be built on an unverified substrate.

## Goal

Deliver a real, runnable `cognee==0.5.5`-backed memory foundation that:

- uses `cognee` as the primary memory provider;
- starts through documented local project commands;
- persists real session-scoped memory in the configured backend stack;
- injects memory into agent runtime and long-text FSM lifecycle;
- exposes enough operational hooks to support later Session-to-KG promotion;
- includes tests and an executable smoke path for sub-flow and subagent startup.

## Storage Boundary

This step must preserve the project's required storage separation:

- `cognee` is used only for memory, dedup, entity/graph extraction, and future promotion handoff.
- For the currently installed version, the project defaults are `graph_database_provider=kuzu` and `vector_database_provider=lancedb`.
- `pgvector` remains the RAG store and must not be merged with or repurposed as the `cognee` memory backend.
- `SessionMemory.cleanup()` may return promotion-ready metadata, but it must not collapse the memory store and RAG store into a single responsibility.
- This lane must not change the architectural rule that RAG storage and memory storage serve different concerns.

## Non-Goals

- Completing full Step `4.4` Knowledge Graph promotion logic.
- Redesigning the overall agent architecture.
- Replacing Redis Streams, DAG scheduling, or prompt architecture.
- Introducing LangChain, LlamaIndex, Celery, socket.io, or Redis Pub/Sub.

## Chosen Approach

Use `cognee` directly as the production memory backend and treat graceful degradation as a controlled fallback path, not the primary implementation.

The work is divided into four layers:

1. **Infrastructure layer**
- install and configure `cognee` and required services;
- align project config and docs to the latest installable `cognee==0.5.5` contract;
- provide deterministic startup and health-check paths;
- keep `MEMORY_ENABLED=false` as an explicit escape hatch.

2. **Memory API layer**
   - turn `MemoryAdapter` into a real `cognee` integration boundary;
   - keep `SessionMemory` as the stable project-facing API;
   - make namespace isolation and error surfacing explicit.

3. **Runtime lifecycle layer**
   - wire FSM transitions to session initialization, territory map storage, and cleanup/promotion handoff;
   - wire agent middleware to before/after task memory reads and writes.

4. **Operations and verification layer**
   - provide scripts/commands to boot memory dependencies and validate them;
   - prove one real task flow can start sub-flows and subagents with memory enabled.

## Step Mapping

### Step 4.1

**Deliverable:** real `cognee` adapter and stable `SessionMemory` contract.

**Touched files:**
- `backend/app/memory/config.py`
- `backend/app/memory/adapter.py`
- `backend/app/memory/session.py`
- `backend/tests/test_memory_core.py`

**Required tests:**
- unit tests for enabled-mode provider resolution;
- unit tests for namespace isolation and session lifecycle;
- unit tests for visible failure semantics when memory is enabled and provider bootstrap fails.

**Exit criteria:**
- `MEMORY_ENABLED=true` uses a real `cognee` path instead of the current generic wrapper behavior;
- unit tests prove round-trip contract against injected fake provider objects;
- unsupported backend combinations such as `neo4j/qdrant` fail explicitly and diagnostically;
- config remains compatible with project `.env` loading.

### Step 4.1a

**Deliverable:** runtime binding between memory lifecycle, middleware, and long-text FSM.

**Touched files:**
- `backend/app/agents/middleware.py`
- `backend/app/services/long_text_fsm.py`
- `backend/tests/test_memory_middleware.py`
- `backend/tests/test_long_text_fsm.py`

**Required tests:**
- middleware before/after task memory IO;
- FSM transition hooks for initialize/store/cleanup;
- checkpoint fields needed for session re-attachment.

**Exit criteria:**
- `MemoryMiddleware` remains in pipeline order `Logging -> TokenTracking -> Timeout -> ContextSummary -> Memory -> Agent`;
- outline/writer/reviewer/consistency flows can read/write session memory through the runtime path;
- FSM terminal path performs cleanup handoff without bypassing middleware ordering or state guards.

### Step 4.1b

**Deliverable:** startup, real integration proof, smoke scenario, and truthful docs.

**Touched files:**
- `docker-compose.yml`
- `backend/tests/test_memory_components.py`
- `backend/tests/test_agent_core.py`
- `scripts/start_memory_stack.ps1`
- `scripts/check_memory_stack.ps1`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/progress.md`
- `docs/task_plan.md`

**Required tests/checks:**
- local integration test for one `cognee` namespace round-trip;
- backend startup check under `MEMORY_ENABLED=true`;
- one named smoke path showing agent runtime receives memory context.

**Exit criteria:**
- documented startup commands succeed locally;
- smoke scenario passes with concrete observable evidence;
- project docs stop claiming the lane is complete until these checks are true.

## Design Details

### 1. Real Cognee Integration

`backend/app/memory/adapter.py` will become the only place that knows how to talk to `cognee`.

Responsibilities:

- resolve and cache a real `cognee` client/runtime;
- initialize provider-specific resources once;
- expose project-safe async methods for add/search/cognify and any cleanup/bootstrap call needed by runtime;
- raise or log actionable failures instead of silently masking all provider issues.

Constraints:

- Business code must not import `cognee` directly outside the adapter boundary.
- When memory is enabled but `cognee` is unavailable, logs and tests must make the failure visible.
- Fallback to no-op remains allowed only when `MEMORY_ENABLED=false` or an explicitly tested degradation path is used.

### 2. SessionMemory as Stable Contract

`backend/app/memory/session.py` remains the single task-scoped API.

Required lifecycle:

- `initialize(task_id)` creates/attaches the session namespace.
- `store_*` methods write chapter summaries, review summaries, and territory/claim data.
- `query_*` methods retrieve dedup and review context for the current task.
- `cleanup()` finalizes the session and returns enough metadata for later promotion hooks.

This preserves the existing project architecture: middleware and FSM depend on `SessionMemory`, not on `cognee` directly.

### 3. FSM and Middleware Binding

The completion standard for `4.1` now includes runtime binding, not just standalone memory code.

Required behavior:

- entering `OUTLINE` initializes session memory;
- outline completion stores territory/topic claims;
- writer/reviewer/consistency flows receive memory context via `MemoryMiddleware.before_task`;
- chapter/review outputs are written back through `MemoryMiddleware.after_task`;
- entering terminal completion path triggers cleanup and prepares the handoff point for later KG promotion.

`backend/app/services/long_text_fsm.py` owns state-transition hooks.

`backend/app/agents/middleware.py` owns per-task memory IO.

Mandatory ordering rule:

- `MemoryMiddleware` must remain in the pipeline order `Logging -> TokenTracking -> Timeout -> ContextSummary -> Memory -> Agent`.
- New memory hooks must preserve this order instead of moving memory access ahead of context compression.

### 4. Startup and Sub-Flow Readiness

The user explicitly requires that sub-flows and subagents can be started correctly after this lane.

That means this design must result in:

- a reproducible way to boot memory dependencies locally;
- a reproducible way to start the backend with memory enabled;
- at least one validated path showing agent execution receives and writes memory context;
- documentation that makes the runtime steps unambiguous for the next session.

### Named Smoke Scenario: `memory_enabled_writer_roundtrip`

This lane will use one explicit smoke scenario as the readiness check for Step `4.1b`.

**Env vars:**
- `MEMORY_ENABLED=true`
- `COGNEE_VERSION=0.5.5`
- `GRAPH_DATABASE_PROVIDER=kuzu`
- `VECTOR_DATABASE_PROVIDER=lancedb`

**Startup commands:**
- `powershell -ExecutionPolicy Bypass -File scripts/start_memory_stack.ps1`
- `powershell -ExecutionPolicy Bypass -File scripts/check_memory_stack.ps1`
- `.\backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_memory_components.py`

**Task fixture:**
- one technical-report task fixture with a title-only entry path that reaches `OUTLINE` then launches at least one writer-oriented runtime step.

**Sub-flow/subagent expectation:**
- the writer runtime path starts with memory enabled;
- `MemoryMiddleware.before_task` injects non-empty session context after at least one prior memory write;
- `MemoryMiddleware.after_task` writes the chapter summary back to the session namespace.

**Observable evidence:**
- backend test/log evidence that the task-specific namespace is created;
- at least one successful add/search or equivalent adapter round-trip under that namespace;
- FSM or runtime checkpoint data retains enough session metadata to support later promotion.

**Pass/fail:**
- PASS only if startup commands succeed and the runtime path both reads and writes task-scoped memory.
- FAIL if the flow silently downgrades to no-op while `MEMORY_ENABLED=true`, or if the writer path starts without usable memory context.

### 5. Test Strategy

Tests must be layered:

- **Unit tests**
  - adapter behavior around `cognee` client resolution;
  - session lifecycle and namespace behavior;
  - middleware before/after memory interactions;
  - FSM transition-triggered memory hooks.

- **Integration tests**
  - real `cognee` connectivity against local dependency stack;
  - session write/search/cognify cycle;
  - backend startup with memory enabled.

- **Smoke/E2E verification**
  - one task path that starts the relevant sub-flow and proves memory lifecycle events occur.

Mocks remain valid for pure unit coverage, but this lane is not complete without at least one real integration path.

## Test Policy

- Unit tests must remain local-only and use project-safe fakes/mocks such as `MockLLMClient` and `fakeredis` where applicable.
- Integration tests for this lane must use only local dependencies and must not call remote model APIs.
- No test lane may call external APIs.
- Required named suites:
  - unit: `backend/tests/test_memory_core.py`, `backend/tests/test_memory_middleware.py`, `backend/tests/test_long_text_fsm.py`
  - integration: `backend/tests/test_memory_components.py`
  - smoke: targeted runtime verification in `backend/tests/test_agent_core.py`

## Files Expected to Change

- `backend/app/memory/config.py`
- `backend/app/memory/adapter.py`
- `backend/app/memory/session.py`
- `backend/app/agents/middleware.py`
- `backend/app/services/long_text_fsm.py`
- `backend/tests/test_memory_core.py`
- `backend/tests/test_memory_middleware.py`
- `backend/tests/test_memory_components.py`
- `backend/tests/test_long_text_fsm.py`
- `backend/tests/test_agent_core.py`
- `scripts/start_memory_stack.ps1`
- `scripts/check_memory_stack.ps1`
- project startup/config files for Docker or local service boot
- `backend/tests/*` for unit and integration coverage
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/progress.md`
- `docs/task_plan.md`

## Risks and Mitigations

1. **`cognee` API mismatch with current assumptions**
   - Mitigation: adapter-first TDD and a real integration probe before broad runtime wiring.

2. **Latest package line no longer matching old `neo4j/qdrant` assumptions**
   - Mitigation: freeze project defaults to `kuzu/lancedb` for `0.5.5`, and reject unsupported combinations explicitly.

3. **Silent fallback masking production issues**
   - Mitigation: make enabled-mode provider failures observable and test them explicitly.

4. **FSM hook side effects causing regressions**
   - Mitigation: bind lifecycle incrementally with isolated tests before running broader suites.

5. **Environment complexity on local Windows setup**
   - Mitigation: codify startup scripts and avoid hand-wavy manual steps.

## Acceptance Criteria

This design is considered implemented only when all of the following are true:

- `cognee` is the active memory path when `MEMORY_ENABLED=true`.
- local startup steps for memory dependencies are documented and runnable.
- `SessionMemory` works against the real backend stack, not only mocks.
- `MemoryMiddleware` reads and writes real memory context in agent flow.
- FSM lifecycle hooks initialize and finalize session memory correctly.
- at least one real task flow demonstrates that sub-flows/subagents can run with memory enabled.
- progress and implementation docs are updated to reflect the new truthful state.

## Deferred Work

The following remain intentionally deferred beyond this design:

- full `KnowledgeGraph` implementation under Step `4.4`;
- promotion ranking policy beyond a stable cleanup/promote handoff contract;
- advanced dedup quality metrics not required to make `4.1` production-ready.

