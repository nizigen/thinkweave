# Dev QA Loop Mock LLM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make local/browser QA flows executable without real LLM API keys by adding a debug-only mock LLM path, then verify frontend and backend behavior through API and browser checks.

**Architecture:** Add an explicit backend setting for mock LLM mode and route `get_llm_client()` to a deterministic mock implementation only when the flag is enabled. Cover the flag and task-creation path with backend tests, then run real local API and browser smoke checks against the running app.

**Tech Stack:** FastAPI, Pydantic Settings, pytest, existing backend task services, Playwright-based browser smoke checks.

---

### Task 1: Add failing tests for mock-LLM debug mode

**Files:**
- Modify: `backend/tests/test_task_api.py`
- Test: `backend/tests/test_task_api.py`

- [ ] **Step 1: Write the failing test**

Add tests that prove:
1. `create_task` succeeds when mock-LLM mode is enabled and API keys are placeholders.
2. `create_task` still returns `503` when mock-LLM mode is disabled and providers are unavailable.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_task_api.py -k "mock_llm or unavailable"`
Expected: FAIL because no runtime mock-LLM switch exists.

- [ ] **Step 3: Write minimal implementation**

Implement only the config/client wiring required to satisfy the test.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_task_api.py -k "mock_llm or unavailable"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_task_api.py backend/app/config.py backend/app/routers/tasks.py backend/app/utils/llm_client.py
git commit -m "feat: add debug mock llm mode"
```

### Task 2: Wire deterministic mock responses into task decomposition flow

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/routers/tasks.py`
- Modify: `backend/app/utils/llm_client.py`
- Test: `backend/tests/test_task_api.py`

- [ ] **Step 1: Add failing assertion for returned task shape**

Extend the new test to assert the created task enters the expected initial state and persists.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_task_api.py -k "mock_llm"`
Expected: FAIL on missing deterministic response or incorrect state transition.

- [ ] **Step 3: Implement minimal mock client**

Add a small production-safe mock client that returns deterministic decomposition/review payloads only under the explicit debug flag.

- [ ] **Step 4: Run tests to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest -q tests/test_task_api.py`
Expected: PASS for the modified task API tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/app/routers/tasks.py backend/app/utils/llm_client.py backend/tests/test_task_api.py
git commit -m "fix: unblock local task api qa with mock llm"
```

### Task 3: Document and verify local QA flow

**Files:**
- Modify: `backend/.env.example`
- Modify: `docs/DEPLOYMENT.md`
- Modify: `docs/progress.md`

- [ ] **Step 1: Write the failing documentation expectation**

Capture the needed docs changes in a small note before editing:
1. local QA flag name
2. dev-only warning
3. browser/API smoke sequence

- [ ] **Step 2: Apply minimal doc updates**

Document how to enable mock-LLM mode locally and warn against production use.

- [ ] **Step 3: Run verification commands**

Run:
`cd backend && .venv/bin/python -m pytest -q tests/test_task_api.py`

Then:
`cd /root/github/agentic-nexus && bash full_api_test.sh`

Expected: task creation no longer returns `503` in local QA mode.

- [ ] **Step 4: Perform browser smoke check**

Use the configured Playwright path if available; otherwise use the local Playwright runtime directly to verify:
1. app loads
2. navigation renders
3. task creation UI responds

- [ ] **Step 5: Commit**

```bash
git add backend/.env.example docs/DEPLOYMENT.md docs/progress.md
git commit -m "docs: add local qa flow for mock llm mode"
```
