# Phase 5.4 WebSocket Connection Layer Design

Date: 2026-03-24
Status: Draft
Scope: Phase 5.4 only
Related docs:
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/APP_FLOW.md`
- `docs/TECH_STACK.md`
- `docs/FRONTEND_GUIDELINES.md`

## Goal

Implement the Phase 5.4 frontend WebSocket connection layer for the monitor page, using the existing backend `/ws/task/{task_id}` event channel and the project's current frontend stack (`React 18.3.1`, `Vite 5.4.8`, `Zustand 4.5.5`, native `WebSocket`).

This step must deliver a minimal but production-usable monitoring foundation:
- connect to the task WebSocket endpoint
- expose connection state to UI
- reconnect with exponential backoff up to 5 attempts
- resync the task snapshot through REST after reconnect
- dispatch incoming task events into a dedicated monitor store
- cover the behavior with frontend unit tests

This step does not implement DAG rendering or the full monitor UI panels. It only builds the connection/state substrate required by Phase 5.5 and 5.6.

## Constraints

Derived from project docs and recent backend hardening:

1. Browser WebSocket auth must use a browser-supported handshake path.
   - Native browser `WebSocket` cannot set arbitrary `Authorization` headers.
   - Phase 5.4 therefore standardizes on `Sec-WebSocket-Protocol` to carry auth metadata.
   - Frontend must read `sessionStorage.task_auth_token`.
   - The token must be encoded into a protocol-safe format before being sent.
   - Backend must accept and validate the token from the request subprotocol list while keeping query-token fallback disabled by default.

2. WebSocket messages are backend-defined task events.
   Supported event types currently include:
   - `connected`
   - `node_update`
   - `log`
   - `agent_status`
   - `task_done`
   - `chapter_preview`
   - `review_score`
   - `consistency_result`
   - `dag_update`

3. The monitor page currently exists as a placeholder and must remain visually lightweight in Phase 5.4.

4. The frontend stack currently has no explicit test runner configured.
   - Phase 5.4 therefore includes adding the minimum frontend test tooling needed for hook/store tests.

## Recommended Approach

Use a dedicated `monitorStore` plus a `useTaskWebSocket(taskId)` hook.

### Why this approach

This is the best fit for the current roadmap because Phase 5.5 and 5.6 will add DAG state, logs, previews, and review scores. Mixing that into the existing `taskStore` would create a broad, unstable store with unrelated concerns. A dedicated monitor store keeps task CRUD/list state separate from real-time monitoring state and reduces refactor pressure in the next two steps.

## Rejected Alternatives

### Option A: Extend `taskStore`

Pros:
- fewer files in the short term

Cons:
- couples task list/detail state with streaming monitor state
- likely to create churn in Phase 5.5 and 5.6
- makes testing reconnect/event logic noisier

Decision: reject

### Option B: Hook-local state only

Pros:
- fastest one-off implementation

Cons:
- poor reuse for future monitor components
- hard to share with DAG, log, preview, and score panels
- would likely require rework in the next step

Decision: reject

## Target Files

### New files

- `frontend/src/hooks/useTaskWebSocket.ts`
- `frontend/src/stores/monitorStore.ts`
- `frontend/src/api/tasks.ts`
- `frontend/src/hooks/__tests__/useTaskWebSocket.test.ts`
- `frontend/vitest.config.ts`
- `frontend/src/test/setup.ts`

### Updated files

- `frontend/package.json`
- `frontend/src/pages/Monitor.tsx`
- `frontend/package-lock.json`
- `backend/app/routers/ws.py`
- `backend/tests/test_ws_endpoint.py`
- `docs/TECH_STACK.md`

## Data Model

Create a dedicated monitor store with these fields:

- `activeTaskId: string | null`
- `connectionState: 'connecting' | 'connected' | 'disconnected' | 'error'`
- `lastError: string | null`
- `reconnectAttempt: number`
- `lastEventAt: number | null`
- `taskSnapshot: Task | null`
- `events: TaskEvent[]`
- `maxRetainedEvents: number`

Where:
- `Task` is the existing task summary/detail shape used by the frontend
- `TaskEvent` is a frontend mirror of the backend WS event envelope

Retention policy:
- keep only the latest `500` raw events in memory
- drop the oldest entries when the cap is exceeded

The event list should remain intentionally simple in Phase 5.4 and can later become the source for DAG/log/preview selectors.

## Store Actions

- `reset(taskId?: string): void`
  - clear the monitoring state when the page switches task or unmounts

- `setConnectionState(state, error?): void`
  - central source of truth for UI connection indicator

- `setTaskSnapshot(task: Task | null): void`
  - store the latest REST-synced task snapshot

- `markReconnectAttempt(count: number): void`
  - keep reconnect count visible for UI and test assertions

- `ingestEvent(event: TaskEvent): void`
  - append event into `events`
  - trim `events` to the latest `500`
  - update `lastEventAt`
  - set `connectionState='connected'` on `connected`
  - optionally update `taskSnapshot.status` / `taskSnapshot.fsm_state` when safe to infer from `task_done` or `dag_update`

Phase 5.4 intentionally avoids over-modeling all event-specific derived state. That work belongs to 5.5 and 5.6 once the monitor UI components exist.

## Hook Contract

`useTaskWebSocket(taskId: string | undefined): { connectionState, lastError, reconnectAttempt }`

Responsibilities:

1. Read auth token from `sessionStorage.task_auth_token`.
2. Build WS URL for `/ws/task/{taskId}` using the current browser protocol/host.
3. Open a native `WebSocket`.
4. Pass auth during handshake via `Sec-WebSocket-Protocol` using a protocol-safe encoded token.
5. Parse incoming JSON messages and dispatch them to `monitorStore.ingestEvent`.
6. Track connection lifecycle:
   - initial connect -> `connecting`
   - successful handshake -> `connected`
   - socket close -> `disconnected`
   - unrecoverable failure -> `error`
7. Reconnect with capped exponential backoff:
   - 1s -> 2s -> 4s -> 8s -> 16s
   - maximum 5 retries
8. After a reconnect opens successfully, call REST `GET /api/tasks/{id}` to restore latest task snapshot.
9. Clean up socket and timers on unmount or task switch.

## Handshake / Auth Strategy

Phase 5.4 makes this concrete:

- frontend opens the socket as:
  - `new WebSocket(url, ["agentic-nexus.auth", "auth.<base64url-token>"])`
- backend reads `websocket.headers["sec-websocket-protocol"]`
- backend extracts the encoded token from the second protocol entry
- backend decodes the base64url value back to the original auth token
- backend authenticates that token with the existing token map
- backend accepts the connection with the single selected subprotocol `"agentic-nexus.auth"`

Rules:
- query-token fallback stays disabled by default
- no cookie/session auth is added in this step
- no proxy-specific header injection is used in this step
- base64url encoding must be used without padding so the auth payload remains a valid subprotocol token

Stage 2 must therefore include both frontend and backend changes for this handshake contract.

## REST Sync

Add `frontend/src/api/tasks.ts` with a minimal `getTask(taskId)` helper built on the existing Axios client.

REST sync should occur:
- once after hook mount, to seed `taskSnapshot`
- once after each successful reconnect, to recover any missed state while disconnected

REST sync should not run on every WS event.

## Monitor Page Changes

In Phase 5.4, `frontend/src/pages/Monitor.tsx` should remain intentionally minimal:

- call `useTaskWebSocket(taskId)`
- read `connectionState`, `reconnectAttempt`, and `lastError` from store
- render the task id
- render an Ant Design status indicator / text summary

No DAG, log stream, preview panel, or score badges yet.

## Testing Strategy

Phase 5.4 requires frontend tests, so add a minimal test setup:

- `vitest@4.1.1`
- `@testing-library/react@16.3.2`
- `@testing-library/jest-dom@6.9.1`
- `jsdom@29.0.1`

This step must also update `docs/TECH_STACK.md` to pin the same frontend test-tool versions.

Test targets:

1. store behavior
   - `reset`
   - `setConnectionState`
   - `ingestEvent`

2. hook behavior
   - opens socket for valid task id
   - transitions to `connected` when `connected` event arrives
   - dispatches incoming events into store
   - schedules reconnect with exponential backoff after close
   - stops retrying after 5 failures
   - triggers REST resync after reconnect success
   - cleans up timers and socket on unmount

3. integration-lite page behavior
   - monitor page shows connection state from the hook/store

## Risks

### Risk 1: Browser WebSocket auth limitations

The browser-compatible auth path now depends on the backend correctly supporting `Sec-WebSocket-Protocol` token parsing, base64url decoding, and framework-compatible subprotocol selection during handshake.

Mitigation:
- implement and test the backend parser in the first RED/GREEN cycle
- keep the auth wiring isolated in the hook
- fail fast when no token exists in `sessionStorage`

### Risk 2: Overbuilding event-specific state too early

Trying to fully model logs, DAG nodes, previews, and scores in Phase 5.4 would create churn before the UI exists.

Mitigation:
- store raw events first
- defer detailed selectors and derived structures to Phase 5.5/5.6

### Risk 3: Reconnect storms

Rapid reconnect loops can hammer the backend.

Mitigation:
- bounded exponential backoff
- hard cap at 5 attempts
- clear timers on unmount/task switch

## Acceptance Criteria

Phase 5.4 is complete when:

1. A dedicated `monitorStore` exists and holds WebSocket connection state.
2. `useTaskWebSocket(taskId)` opens and manages a task-specific connection using the agreed `Sec-WebSocket-Protocol` auth handshake.
3. Incoming JSON task events are parsed and dispatched into the store.
4. Raw events are retained with a hard cap of `500`.
5. Reconnect uses exponential backoff and stops after 5 attempts.
6. REST task resync runs after reconnect success.
7. `Monitor.tsx` visibly reflects connection state.
8. Frontend unit tests exist and pass for the hook/store behavior.
9. Backend WebSocket endpoint tests cover the subprotocol auth path.

## Stage 2 TDD Breakdown Preview

1. RED: add failing backend and frontend tests for the subprotocol auth handshake, store cap, and hook skeleton.
2. GREEN: implement backend subprotocol auth support, `monitorStore`, task API helper, and the first working WebSocket lifecycle.
3. REFACTOR: clean connection helpers, event trimming, and auth parsing boundaries.
4. RED: add reconnect and resync failure tests.
5. GREEN: implement exponential backoff and post-reconnect task sync.
6. REFACTOR: simplify timer cleanup and guard conditions.
