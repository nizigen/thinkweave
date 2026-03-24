# Step 4.2 Agent Contract Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the specialized long-text runtime agents and memory middleware so Step 4.2 matches the approved contract design while remaining aligned with the repo's current FSM and runtime workflow.

**Architecture:** Keep the existing three-layer runtime architecture and strengthen only the execution-layer contracts. Specialized agents stay as `outline`, `writer`, `reviewer`, and `consistency`, while `MemoryMiddleware` becomes the role-aware context handoff layer that injects and persists task-scoped memory artifacts.

**Tech Stack:** FastAPI runtime agents, PromptLoader, session memory adapter, pytest, Docker-backed local services

---

### Task 1: Write Contract-Focused Failing Tests

**Files:**
- Modify: `backend/tests/test_specialized_agents.py`
- Modify: `backend/tests/test_memory_middleware.py`
- Modify: `backend/tests/test_agent_core.py`
- Create: `backend/tests/test_agent_prompt_contracts.py`

- [ ] **Step 1: Write failing tests for upgraded specialized-agent payload contracts**

Add tests that expect:
- `OutlineAgent` to pass through optional `draft_text`, `review_comments`, and `style_requirements`.
- `WriterAgent` to require and forward `topic_claims` and `assigned_evidence`.
- `ReviewerAgent` to preserve overlap and scope-related fields.
- `ConsistencyAgent` to normalize `topic_claims` and `chapter_metadata`.

- [ ] **Step 2: Write failing tests for memory middleware role-specific behavior**

Add tests that expect:
- default middleware order includes `MemoryMiddleware` after `ContextSummaryMiddleware`.
- outline after-task writes both summary data and territory map.
- writer before-task receives non-empty memory context after prior writes.
- reviewer and consistency roles receive distinct memory injection patterns.

- [ ] **Step 3: Write failing prompt contract tests**

Add tests that assert prompt templates explicitly mention:
- topic territory / topic claims in outline prompt;
- evidence usage and chapter boundaries in writer prompt;
- evidence sufficiency and boundary compliance in reviewer prompt;
- issue families in consistency prompt.

- [ ] **Step 4: Run targeted tests to verify RED state**

Run: `..venv\Scripts\python.exe -m pytest -q tests/test_specialized_agents.py tests/test_memory_middleware.py tests/test_agent_core.py tests/test_agent_prompt_contracts.py`

Expected: one or more failures caused by the new contract assertions.

- [ ] **Step 5: Commit test-only RED state**

```bash
git add backend/tests/test_specialized_agents.py backend/tests/test_memory_middleware.py backend/tests/test_agent_core.py backend/tests/test_agent_prompt_contracts.py
git commit -m "test: add step 4.2 contract upgrade coverage"
```

### Task 2: Implement Role-Aware Memory Middleware and Default Pipeline Wiring

**Files:**
- Modify: `backend/app/agents/middleware.py`
- Modify: `backend/app/memory/session.py`
- Modify: `backend/tests/test_memory_middleware.py`
- Modify: `backend/tests/test_agent_core.py`

- [ ] **Step 1: Implement `MemoryMiddleware` in runtime middleware module**

Add a real `MemoryMiddleware` class to `backend/app/agents/middleware.py` with:
- `session_factory(task_id)` support;
- `before_task()` role-aware injection logic;
- `after_task()` role-aware persistence logic;
- no-op graceful degradation when memory is disabled.

- [ ] **Step 2: Insert `MemoryMiddleware` into `DEFAULT_MIDDLEWARES` in the required order**

Required order:
- `LoggingMiddleware()`
- `TokenTrackingMiddleware()`
- `TimeoutMiddleware()`
- `ContextSummaryMiddleware()`
- `MemoryMiddleware()`

- [ ] **Step 3: Extend `SessionMemory` only as needed to support role-aware storage/query metadata**

Add the smallest API improvements needed for middleware to store:
- outline summary / territory map;
- writer chapter summary and evidence metadata;
- reviewer summary metadata;
- consistency issue summary.

- [ ] **Step 4: Run targeted middleware tests to verify GREEN state**

Run: `..venv\Scripts\python.exe -m pytest -q tests/test_memory_middleware.py tests/test_agent_core.py -k "MemoryMiddleware or default_middlewares_count or memory_enabled_writer_roundtrip"`

Expected: PASS.

- [ ] **Step 5: Refactor for clarity and rerun the same tests**

Keep middleware behavior explicit by role and avoid hidden magic field names where possible.

### Task 3: Upgrade Specialized Agent Payload Contracts

**Files:**
- Modify: `backend/app/agents/outline_agent.py`
- Modify: `backend/app/agents/writer_agent.py`
- Modify: `backend/app/agents/reviewer_agent.py`
- Modify: `backend/app/agents/consistency_agent.py`
- Modify: `backend/app/agents/worker.py`
- Modify: `backend/tests/test_specialized_agents.py`

- [ ] **Step 1: Implement stricter normalization in each specialized agent**

Upgrade payload normalization so each agent exposes the approved contract fields and stable defaults.

- [ ] **Step 2: Tighten `WorkerAgent` prompt-building behavior where required**

Preserve prompt loading, but ensure structured values such as lists and dicts serialize consistently for prompt templates.

- [ ] **Step 3: Run specialized agent tests**

Run: `..venv\Scripts\python.exe -m pytest -q tests/test_specialized_agents.py`

Expected: PASS.

- [ ] **Step 4: Add or adjust one regression assertion in `test_agent_core.py` if worker serialization changed**

Run: `..venv\Scripts\python.exe -m pytest -q tests/test_agent_core.py -k "WorkerAgent or process_task"`

Expected: PASS.

- [ ] **Step 5: Refactor comments/docstrings for readability and rerun the same tests**

### Task 4: Upgrade Prompt Contracts to Match the New Agent Design

**Files:**
- Modify: `backend/prompts/outline/generate.md`
- Modify: `backend/prompts/writer/write_chapter.md`
- Modify: `backend/prompts/reviewer/review_chapter.md`
- Modify: `backend/prompts/consistency/check.md`
- Modify: `backend/tests/test_agent_prompt_contracts.py`

- [ ] **Step 1: Update outline prompt to require structure, ownership, and boundaries**

Prompt must explicitly require:
- chapter progression;
- context bridges;
- machine-readable `topic_claims`;
- section/evidence placeholders for downstream writing.

- [ ] **Step 2: Update writer prompt to require evidence-aware, territory-bounded drafting**

Prompt must explicitly mention:
- `topic_claims`;
- `assigned_evidence`;
- `memory_context` as anti-overlap guidance;
- transition continuity.

- [ ] **Step 3: Update reviewer prompt rubric and consistency prompt schema**

Reviewer prompt must include:
- evidence sufficiency;
- boundary compliance;
- non-overlap.

Consistency prompt must include structured issue families:
- style conflicts;
- claim conflicts;
- duplicate coverage;
- term inconsistency;
- transition gaps;
- repair targets.

- [ ] **Step 4: Run prompt contract tests**

Run: `..venv\Scripts\python.exe -m pytest -q tests/test_agent_prompt_contracts.py tests/test_specialized_agents.py`

Expected: PASS.

- [ ] **Step 5: Refactor wording for clarity without weakening contract assertions**

### Task 5: Full Step 4.2 Regression and Review Gates

**Files:**
- Modify: `docs/progress.md`
- Modify: `docs/task_plan.md`
- Verify touched implementation and test files from prior tasks

- [ ] **Step 1: Run the full targeted Step 4.2 regression suite**

Run: `..venv\Scripts\python.exe -m pytest -q tests/test_specialized_agents.py tests/test_memory_middleware.py tests/test_agent_core.py tests/test_agent_prompt_contracts.py tests/test_review_fixes.py tests/test_llm_client.py tests/test_task_api.py tests/test_agents.py tests/test_long_text_fsm.py::TestCheckpoint tests/test_memory_core.py`

Expected: PASS.

- [ ] **Step 2: Perform code review against touched files**

Required output:
- findings with severity and file reference;
- fix any CRITICAL/HIGH issues before proceeding.

- [ ] **Step 3: Perform security review against touched files**

Check:
- prompt injection trust boundaries;
- memory context contamination;
- structured output assumptions;
- hidden privilege flow through middleware.

- [ ] **Step 4: Update progress-tracking docs with Step 4.2 completion evidence**

Record:
- contract upgrade completed;
- memory middleware integrated in default pipeline;
- targeted regression command and result.

- [ ] **Step 5: Commit implementation and review closure**

```bash
git add backend/app/agents backend/app/memory backend/prompts backend/tests docs/progress.md docs/task_plan.md
git commit -m "feat: complete step 4.2 agent contract upgrade"
```
