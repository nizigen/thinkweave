## External Reference Alignment

Execution ordering is aligned with reusable Aletheia planning patterns (memory-first lifecycle closure, then promotion lane),
but implementation truth for provider/runtime compatibility is taken from this repository's tested environment and tests.
# Cognee Memory Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Mandatory tri-plugin order:** `Stage 1 planning signoff -> Stage 2 RED/GREEN/REFACTOR implementation -> Stage 3 code review + security review + verification-before-completion`.
>
> **Blocking gates:**
> - Do not start implementation before this spec and plan are approved.
> - Do not do broad runtime wiring before a real enabled-mode `cognee` integration probe passes.
> - Do not claim completion before code review, security review, and final startup/smoke verification pass.

**Goal:** Complete Step `4.1 + 4.1a + 4.1b` by integrating real `cognee==0.5.5` memory, wiring runtime lifecycle hooks, and making the startup/sub-flow path runnable and verifiable.

**Architecture:** Keep `SessionMemory` as the project-facing contract, but make `MemoryAdapter` the real `cognee` boundary. Bind the memory lifecycle into FSM transitions and agent middleware, then add operational scripts and integration verification so the lane is usable, not just coded.

**Tech Stack:** FastAPI, SQLAlchemy async, pytest, Docker Compose/local services, `cognee==0.5.5`, Kuzu, LanceDB, Redis, PostgreSQL

---

### File Structure

- `backend/app/memory/config.py`
  - Memory feature flags and provider settings aligned to `cognee==0.5.5`.
- `backend/app/memory/adapter.py`
  - Real `cognee` integration boundary, provider bootstrap, and backend-matrix validation.
- `backend/app/memory/session.py`
  - Stable task-scoped memory API used by runtime code.
- `backend/app/agents/middleware.py`
  - Reads memory before agent execution and writes memory summaries after execution.
- `backend/app/services/long_text_fsm.py`
  - Triggers memory lifecycle hooks on state transitions.
- `backend/tests/test_memory_core.py`
  - Unit coverage for adapter/session lifecycle.
- `backend/tests/test_agent_core.py`
  - Middleware and runtime integration unit coverage.
- `backend/tests/test_long_text_fsm.py`
  - FSM memory-hook coverage.
- `backend/tests/test_memory_components.py`
  - Real `cognee` connectivity and local readiness checks.
- `scripts/start_memory_stack.ps1`
  - Local startup helper for the supported local dependency set.
- `scripts/check_memory_stack.ps1`
  - Local health-check helper for memory dependencies.
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/progress.md`
- `docs/task_plan.md`

### Task 1: Lock the Real Cognee Contract

**Files:**
- Modify: `backend/app/memory/adapter.py`
- Test: `backend/tests/test_memory_core.py`

- [ ] **Step 1: Write failing adapter tests for enabled-mode cognee behavior**

Add tests that assert:
- enabled mode resolves a real provider object;
- provider failures in enabled mode are surfaced/logged predictably;
- unsupported backend matrices are rejected explicitly for `cognee==0.5.5`;
- `add/search/cognify` forward correct namespace and payload;
- disabled mode still returns no-op behavior.

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `.\backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_memory_core.py -k "adapter or cognee"`
Expected: FAIL because current adapter is still only a generic wrapper.

- [ ] **Step 3: Implement minimal real cognee adapter**

Implement:
- provider resolution/bootstrap methods;
- explicit enabled/disabled semantics;
- async wrappers for add/search/cognify;
- actionable error handling for enabled-mode failures.

- [ ] **Step 4: Re-run targeted tests**

Run: `.\backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_memory_core.py -k "adapter or cognee"`
Expected: PASS

- [ ] **Step 5: Refactor for clarity**

Clean up naming, helper boundaries, and duplicate error handling without changing behavior.

### Task 2: Complete SessionMemory Lifecycle

**Files:**
- Modify: `backend/app/memory/session.py`
- Test: `backend/tests/test_memory_core.py`

- [ ] **Step 1: Write failing lifecycle tests**

Add tests for:
- initialize attaches deterministic namespace;
- territory map storage uses the intended adapter API;
- chapter/review summary store/query helpers behave correctly;
- cleanup returns/records the final state required for later promotion handoff.

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `.\backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_memory_core.py -k "SessionMemory"`
Expected: FAIL because current API is too thin for the required lifecycle.

- [ ] **Step 3: Implement the smallest session API that satisfies runtime needs**

Implement or expand:
- `initialize`
- summary/territory store helpers
- query helpers for runtime context
- cleanup/finalization contract

- [ ] **Step 4: Re-run targeted tests**

Run: `.\backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_memory_core.py -k "SessionMemory"`
Expected: PASS

- [ ] **Step 5: Refactor**

Keep the external contract small and remove duplicate namespace initialization logic.

### Task 3: Prove Real Enabled-Mode Cognee Integration Before Runtime Wiring

**Files:**
- Modify: `backend/tests/test_memory_components.py`
- Create: `scripts/start_memory_stack.ps1`
- Create: `scripts/check_memory_stack.ps1`
- Modify: `docker-compose.yml` only if startup/health-check gaps are discovered

- [ ] **Step 1: Write the failing real-integration checks**

Add/expand checks that prove:
- local memory services are reachable;
- one task namespace can perform a real or adapter-probed `cognee` add/search/cognify round-trip under the supported backend matrix;
- enabled mode does not silently downgrade to no-op.

- [ ] **Step 2: Run the local health-check command to verify failure**

Run: `powershell -ExecutionPolicy Bypass -File scripts/check_memory_stack.ps1`
Expected: FAIL or missing checks because startup verification is not yet codified.

- [ ] **Step 3: Implement minimal startup and health-check scripts**

Implement:
- `scripts/start_memory_stack.ps1`
- `scripts/check_memory_stack.ps1`
- any minimal `docker-compose.yml` adjustment required for reproducible local checks

- [ ] **Step 4: Run the real integration test to verify it passes**

Run: `.\backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_memory_components.py`
Expected: PASS with one real namespace round-trip against local services.

- [ ] **Step 5: Refactor**

Keep startup/check scripts deterministic and project-specific. Do not bury required operational steps in prose only.

### Task 4: Wire MemoryMiddleware to the Real Session Contract

**Files:**
- Modify: `backend/app/agents/middleware.py`
- Test: `backend/tests/test_agent_core.py`

- [ ] **Step 1: Write failing middleware tests**

Add tests that assert:
- `before_task` reads real session context using `SessionMemory`;
- writer/reviewer/consistency flows receive the right injected memory payload;
- `after_task` persists expected summaries/metadata;
- disabled memory mode remains pass-through.

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `.\backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_agent_core.py -k "MemoryMiddleware"`
Expected: FAIL for missing or incomplete real-session behavior.

- [ ] **Step 3: Implement minimal middleware changes**

Wire `MemoryMiddleware` to the updated `SessionMemory` contract and keep middleware ordering unchanged.

- [ ] **Step 4: Re-run targeted tests**

Run: `.\backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_agent_core.py -k "MemoryMiddleware"`
Expected: PASS

- [ ] **Step 5: Refactor**

Remove redundant payload-shaping logic and keep context injection explicit.

### Task 5: Bind FSM Transitions to Memory Lifecycle

**Files:**
- Modify: `backend/app/services/long_text_fsm.py`
- Test: `backend/tests/test_long_text_fsm.py`

- [ ] **Step 1: Write failing FSM hook tests**

Add tests for:
- entering `OUTLINE` initializes session memory;
- outline completion stores territory/topic claims;
- terminal completion path triggers cleanup;
- checkpoint data preserves what runtime needs to re-attach the session.

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `.\backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_long_text_fsm.py -k "memory or cleanup or territory"`
Expected: FAIL because lifecycle hooks are not fully implemented.

- [ ] **Step 3: Implement minimal transition hooks**

Add transition-time calls into `SessionMemory` without widening FSM responsibilities beyond lifecycle orchestration.

- [ ] **Step 4: Re-run targeted tests**

Run: `.\backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_long_text_fsm.py -k "memory or cleanup or territory"`
Expected: PASS

- [ ] **Step 5: Refactor**

Extract hook helpers if `transition()` becomes hard to read.

### Task 6: Validate Named Smoke Scenario for Sub-Flow and Subagent Startup

**Files:**
- Modify: `backend/tests/test_agent_core.py`
- Modify: `backend/tests/test_memory_middleware.py`
- Modify: `backend/app/agents/middleware.py` only if smoke assertions reveal a runtime gap
- Modify: `backend/app/services/long_text_fsm.py` only if smoke assertions reveal a lifecycle gap

- [ ] **Step 1: Write the failing smoke-path verification**

Add one named verification path for `memory_enabled_writer_roundtrip` that asserts:
- memory-enabled writer runtime receives injected session context;
- memory-enabled runtime writes a summary back to the task namespace;
- lifecycle metadata needed for later promotion remains present.

- [ ] **Step 2: Run the targeted smoke tests to verify failure**

Run: `.\backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_agent_core.py -k "memory_enabled_writer_roundtrip or MemoryMiddleware"`
Expected: FAIL or incomplete because the full named smoke path is not yet proven.

- [ ] **Step 3: Implement minimal runtime fixes**

Fix only what is required to make the named smoke path real and reproducible.

- [ ] **Step 4: Re-run the targeted smoke tests**

Run: `.\backend\.venv\Scripts\python.exe -m pytest -q backend/tests/test_agent_core.py -k "memory_enabled_writer_roundtrip or MemoryMiddleware"`
Expected: PASS

- [ ] **Step 5: Refactor**

Keep the startup path explicit and avoid hidden coupling.

### Task 7: Truthful Documentation and Regression Pass

**Files:**
- Modify: `docs/IMPLEMENTATION_PLAN.md`
- Modify: `docs/progress.md`
- Modify: `docs/task_plan.md`
- Run: targeted/full regression suites as appropriate

- [ ] **Step 1: Write failing documentation checklist**

Create a checklist of statements that are currently no longer truthful or need updating after real `cognee` integration.

- [ ] **Step 2: Run the final verification commands**

Run the final set of targeted and broader regression tests.

- [ ] **Step 3: Update docs to match reality**

Record:
- what is actually complete;
- what startup path to use;
- what remains deferred for `4.3/4.4`.

- [ ] **Step 4: Re-run the final smoke path**

Expected: PASS with docs matching the executed path.

- [ ] **Step 5: Stop for review gates**

Do not claim completion yet. Proceed to:
- code review sub-flow
- security review sub-flow
- final verification-before-completion evidence

