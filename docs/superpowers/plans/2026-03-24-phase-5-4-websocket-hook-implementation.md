# Phase 5.4 WebSocket Connection Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 5.4 monitor WebSocket connection layer with browser-safe auth handshake, reconnect/resync logic, a dedicated monitor store, and unit test coverage.

**Architecture:** The implementation adds a dedicated frontend `monitorStore` and a `useTaskWebSocket(taskId)` hook, while also extending the backend WebSocket router to support browser authentication via `Sec-WebSocket-Protocol` with base64url-encoded token transport. The monitor page remains lightweight and only surfaces connection state in this step; richer DAG/log/preview rendering is deferred to Phase 5.5 and 5.6.

**Tech Stack:** React 18.3.1, Vite 5.4.8, Zustand 4.5.5, native WebSocket, FastAPI WebSocket router, Vitest 4.1.1, Testing Library React 16.3.2, jest-dom 6.9.1, jsdom 29.0.1.

---

## File Map

- Create: `frontend/src/stores/monitorStore.ts`
- Create: `frontend/src/hooks/useTaskWebSocket.ts`
- Create: `frontend/src/api/tasks.ts`
- Create: `frontend/src/hooks/__tests__/useTaskWebSocket.test.ts`
- Create: `frontend/src/stores/__tests__/monitorStore.test.ts`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/src/pages/Monitor.tsx`
- Modify: `backend/app/routers/ws.py`
- Modify: `backend/tests/test_ws_endpoint.py`
- Modify: `docs/TECH_STACK.md`
- Modify: `docs/progress.md`
- Modify: `docs/task_plan.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

## Task 1: Bootstrap frontend test harness and backend auth test lane

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`
- Modify: `docs/TECH_STACK.md`
- Modify: `backend/tests/test_ws_endpoint.py`

- [ ] **Step 1: Add frontend test dependencies and scripts with exact versions**

Update `frontend/package.json` to add:
- `vitest@4.1.1`
- `@testing-library/react@16.3.2`
- `@testing-library/jest-dom@6.9.1`
- `jsdom@29.0.1`

Also add a `test` script using Vitest.

- [ ] **Step 2: Add Vitest config and test setup**

Create:
- `frontend/vitest.config.ts`
- `frontend/src/test/setup.ts`

Configure:
- `jsdom` environment
- jest-dom registration

- [ ] **Step 3: Update `docs/TECH_STACK.md` with the same pinned test-tool versions**

- [ ] **Step 4: Install frontend test dependencies with a workspace-local npm cache**

Run:
```powershell
$env:npm_config_cache='C:\GitHub\agentic-nexus\frontend\.npm-cache'; npm install
```

Expected: dependencies install without using the restricted global npm cache path.

- [ ] **Step 5: Write backend failing test for subprotocol auth handshake**

Add a test in `backend/tests/test_ws_endpoint.py` that:
- opens the task socket without query token
- sends `sec-websocket-protocol`-compatible values via request headers/mock websocket
- expects the backend to authenticate using the encoded token
- asserts the accepted socket uses `subprotocol="agentic-nexus.auth"`

- [ ] **Step 6: Run the backend test and confirm failure**

Run:
```powershell
backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_ws_endpoint.py -k subprotocol
```

Expected: fail because `ws.py` does not yet parse/decode auth from subprotocol entries.

## Task 2: Add failing frontend store and hook tests

**Files:**
- Create: `frontend/src/stores/__tests__/monitorStore.test.ts`
- Create: `frontend/src/hooks/__tests__/useTaskWebSocket.test.ts`

- [ ] **Step 1: Write failing frontend store tests**

Add tests for:
- `reset`
- `setConnectionState`
- `ingestEvent`
- trimming raw events to the latest `500`

- [ ] **Step 2: Write failing frontend hook tests**

Add tests for:
- open socket on mount
- build socket with `["agentic-nexus.auth", "auth.<base64url-token>"]`
- set `connected` on `connected` event
- dispatch incoming events to store
- no token -> no socket open and connection enters an error/disconnected state

- [ ] **Step 3: Run the frontend tests and confirm failure**

Run:
```powershell
npm run test
```

Expected: fail on missing feature behavior, not on missing test harness.

## Task 3: GREEN for backend auth transport

**Files:**
- Modify: `backend/app/routers/ws.py`
- Modify: `backend/tests/test_ws_endpoint.py`

- [ ] **Step 1: Implement backend subprotocol auth parsing**

In `backend/app/routers/ws.py`:
- add helper(s) to parse `sec-websocket-protocol`
- extract second offered value of the form `auth.<base64url-token>`
- base64url decode it
- authenticate decoded token via the existing token map
- accept the websocket with `subprotocol="agentic-nexus.auth"`

- [ ] **Step 2: Run backend auth tests and verify pass**

Run:
```powershell
backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_ws_endpoint.py -k subprotocol
```

Expected: PASS.

## Task 4: GREEN for monitor store and task API helper

**Files:**
- Create: `frontend/src/stores/monitorStore.ts`
- Create: `frontend/src/api/tasks.ts`
- Create: `frontend/src/stores/__tests__/monitorStore.test.ts`

- [ ] **Step 1: Implement `monitorStore` with the agreed state shape**

Include:
- `activeTaskId`
- `connectionState`
- `lastError`
- `reconnectAttempt`
- `lastEventAt`
- `taskSnapshot`
- `events`
- event retention cap at `500`

- [ ] **Step 2: Implement the store actions**

Include:
- `reset`
- `setConnectionState`
- `setTaskSnapshot`
- `markReconnectAttempt`
- `ingestEvent`

- [ ] **Step 3: Add `frontend/src/api/tasks.ts`**

Expose a minimal `getTask(taskId)` helper built on the existing Axios client.

- [ ] **Step 4: Run the store tests**

Run:
```powershell
npm run test -- monitorStore
```

Expected: PASS.

- [ ] **Step 5: Refactor store helpers if needed**

Keep event trimming and event-type branching small and obvious.

## Task 5: GREEN for `useTaskWebSocket`

**Files:**
- Create: `frontend/src/hooks/useTaskWebSocket.ts`
- Create: `frontend/src/hooks/__tests__/useTaskWebSocket.test.ts`
- Modify: `frontend/src/api/tasks.ts` if extra typing is needed

- [ ] **Step 1: Implement a small helper to encode token to base64url without padding**

Keep it local to the hook module unless reuse becomes obvious.

- [ ] **Step 2: Implement initial socket lifecycle**

Behavior:
- guard missing `taskId`
- guard missing auth token
- create socket with correct protocol list
- set `connecting`
- parse JSON messages
- send all incoming events to `monitorStore.ingestEvent`

- [ ] **Step 3: Implement reconnect loop**

Behavior:
- backoff sequence `1/2/4/8/16`
- max `5` retries
- stop retries on unmount or task switch

- [ ] **Step 4: Implement REST resync**

Behavior:
- initial `getTask(taskId)` fetch on mount
- `getTask(taskId)` after reconnect success
- no token -> do not open a socket and move the connection state into a deterministic non-connected state

- [ ] **Step 5: Run hook tests**

Run:
```powershell
npm run test -- useTaskWebSocket
```

Expected: PASS.

- [ ] **Step 6: Refactor timer cleanup and socket guards**

Keep cleanup deterministic and testable.

## Task 6: Connect the monitor page to the new hook/store

**Files:**
- Modify: `frontend/src/pages/Monitor.tsx`

- [ ] **Step 1: Add hook usage to `Monitor.tsx`**

Call `useTaskWebSocket(taskId)`.

- [ ] **Step 2: Read connection state from `monitorStore`**

Render:
- task id
- connection state
- reconnect attempt
- last error when present

- [ ] **Step 3: Keep UI intentionally minimal**

Do not add DAG graph, preview tabs, or log stream in this task.

- [ ] **Step 4: Run page-related test coverage if added**

If a light integration test is added, run it now.

## Task 7: Refactor and broader verification

**Files:**
- Modify any of the above only if cleanup is behavior-preserving

- [ ] **Step 1: Run the backend WebSocket suite**

Run:
```powershell
backend/.venv/Scripts/python.exe -m pytest -q backend/tests/test_ws_endpoint.py backend/tests/test_ws_manager.py backend/tests/test_event_bridge.py
```

- [ ] **Step 2: Run the frontend Phase 5.4 test suite**

Run:
```powershell
npm run test
```

- [ ] **Step 3: Run frontend lint**

Run:
```powershell
npm run lint
```

- [ ] **Step 4: Record implementation results in docs**

Update:
- `docs/progress.md`
- `docs/task_plan.md`
- `docs/IMPLEMENTATION_PLAN.md`

## Review Gate

- [ ] **Step 1: Run code review sub-flow**
- [ ] **Step 2: Fix any CRITICAL/HIGH code findings**
- [ ] **Step 3: Run security review sub-flow**
- [ ] **Step 4: Fix any CRITICAL/HIGH security findings**
- [ ] **Step 5: Re-run verification after fixes**
