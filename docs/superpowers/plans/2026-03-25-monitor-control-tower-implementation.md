# Monitor Control Tower Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Phase 5.5 and 5.6 by upgrading the existing monitor page into a full Control Tower view with a live DAG, agent activity panel, log stream, FSM progress, chapter preview, and real task control commands for pause, resume, skip, and retry.

**Architecture:** The implementation keeps the current `GET /api/tasks/{id}` plus WebSocket event model and extends it rather than replacing it. Backend task control is added as REST APIs plus a dedicated `task_control` service and small scheduler hooks. Frontend monitor state is normalized in `monitorStore`, with React components rendering from normalized state while G6 remains a pure graph renderer.

**Tech Stack:** FastAPI, SQLAlchemy async, React 18.3.1, Zustand 4.5.5, Ant Design 5.21.0, @antv/g6 5.0.18, react-markdown 9.0.1, framer-motion 11.11.1, Vitest 4.1.1, Testing Library React 16.3.2, pytest.

---

## File Map

- Create: `backend/app/services/task_control.py`
- Modify: `backend/app/routers/tasks.py`
- Modify: `backend/app/schemas/task.py`
- Modify: `backend/app/models/task.py`
- Modify: `backend/app/models/task_node.py`
- Modify: `backend/app/services/task_service.py`
- Modify: `backend/app/services/dag_scheduler.py`
- Modify: `backend/app/services/event_bridge.py`
- Modify: `backend/app/schemas/ws_event.py`
- Create: `backend/tests/test_task_control.py`
- Modify: `backend/tests/test_task_api.py`
- Modify: `backend/tests/test_dag_scheduler.py`
- Modify: `backend/tests/test_event_bridge.py`
- Create: `frontend/src/components/monitor/DagViewer.tsx`
- Create: `frontend/src/components/monitor/AgentPanel.tsx`
- Create: `frontend/src/components/monitor/LogStream.tsx`
- Create: `frontend/src/components/monitor/FsmProgress.tsx`
- Create: `frontend/src/components/monitor/ChapterPreview.tsx`
- Create: `frontend/src/components/monitor/ControlToolbar.tsx`
- Modify: `frontend/src/pages/Monitor.tsx`
- Modify: `frontend/src/stores/monitorStore.ts`
- Modify: `frontend/src/api/tasks.ts`
- Modify: `frontend/src/stores/taskStore.ts`
- Create: `frontend/src/components/monitor/__tests__/DagViewer.test.tsx`
- Create: `frontend/src/components/monitor/__tests__/ControlToolbar.test.tsx`
- Create: `frontend/src/components/monitor/__tests__/MonitorPage.test.tsx`
- Modify: `frontend/src/stores/__tests__/monitorStore.test.ts`
- Modify: `frontend/src/hooks/__tests__/useTaskWebSocket.test.ts`
- Modify: `frontend/src/index.css`
- Modify: `.gitignore`
- Modify: `docs/progress.md`
- Modify: `docs/task_plan.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

## Task 1: RED for backend task control service and APIs

**Files:**
- Create: `backend/tests/test_task_control.py`
- Modify: `backend/tests/test_task_api.py`

- [ ] **Step 1: Write failing service tests for pause and resume legality**

Add tests covering:
- pause allowed when task status is `pending` or `running`
- pause rejected when task is already terminal
- resume allowed only when `checkpoint_data.control.status == "paused"`

- [ ] **Step 2: Write failing service tests for skip and retry**

Add tests covering:
- skip requires `node_id`
- skip allowed for `pending`, `ready`, `running`
- retry allowed only for `failed` and `skipped`
- retry clears terminal execution fields before requeue

- [ ] **Step 3: Write failing API tests for control endpoints**

Add endpoint tests for:
- `POST /api/tasks/{task_id}/control/pause`
- `POST /api/tasks/{task_id}/control/resume`
- `POST /api/tasks/{task_id}/control/skip`
- `POST /api/tasks/{task_id}/control/retry`

Cover:
- happy path
- missing node id for skip/retry
- unauthorized or invisible task returns `404`
- illegal state transition returns `409`

- [ ] **Step 4: Run the new backend tests and confirm failure**

Run:
```bash
cd /root/github/agentic-nexus
backend/.venv/bin/python -m pytest -q backend/tests/test_task_control.py backend/tests/test_task_api.py -k "control or pause or resume or skip or retry"
```

Expected: failure because task control service and routes do not exist yet.

## Task 2: GREEN for backend control service, control persistence, and routes

**Files:**
- Create: `backend/app/services/task_control.py`
- Modify: `backend/app/routers/tasks.py`
- Modify: `backend/app/services/task_service.py`
- Modify: `backend/app/schemas/task.py`

- [ ] **Step 1: Add request/response schemas for control endpoints**

Define small request bodies for:
- skip `{ node_id }`
- retry `{ node_id }`

If reused, add task detail response fields needed by the monitor page.

- [ ] **Step 2: Implement `task_control.py` with small focused functions**

Add functions for:
- `pause_task(...)`
- `resume_task(...)`
- `skip_node(...)`
- `retry_node(...)`

Each function should:
- validate task visibility and command legality
- update `checkpoint_data.control`
- mutate node state when required
- return the refreshed task detail snapshot

- [ ] **Step 3: Make the pause control state machine explicit**

Implement and document the cooperative states:
- immediate command write sets `checkpoint_data.control.status = "pause_requested"`
- scheduler acknowledgment promotes the task to `paused`
- resume is legal only from `paused`

- [ ] **Step 4: Add the REST control routes**

Wire the four control routes in `backend/app/routers/tasks.py`.

- [ ] **Step 5: Run the backend control test lane**

Run:
```bash
cd /root/github/agentic-nexus
backend/.venv/bin/python -m pytest -q backend/tests/test_task_control.py backend/tests/test_task_api.py -k "control or pause or resume or skip or retry"
```

Expected: PASS.

- [ ] **Step 6: Refactor control metadata helpers**

Keep the `checkpoint_data.control` merge/update logic centralized and obvious.

## Task 3: RED/GREEN for scheduler cooperation and event semantics

**Files:**
- Modify: `backend/tests/test_dag_scheduler.py`
- Modify: `backend/tests/test_event_bridge.py`
- Modify: `backend/app/services/dag_scheduler.py`
- Modify: `backend/app/services/event_bridge.py`
- Modify: `backend/app/schemas/ws_event.py`

- [ ] **Step 1: Write failing scheduler tests for pause/resume**

Cover:
- running task enters `pause_requested` immediately and only becomes `paused` after active work settles
- pause prevents future dispatch without interrupting already running nodes
- resume allows ready nodes to dispatch again

- [ ] **Step 2: Write failing scheduler tests for skipped running nodes**

Cover:
- a running node marked skipped cannot later transition to `done` through a stale completion callback

- [ ] **Step 3: Write failing event bridge tests for control-driven monitor updates**

Cover:
- control actions emit monitor-visible updates through supported event types

- [ ] **Step 4: Run scheduler and bridge tests to confirm failure**

Run:
```bash
cd /root/github/agentic-nexus
backend/.venv/bin/python -m pytest -q backend/tests/test_dag_scheduler.py backend/tests/test_event_bridge.py -k "pause or resume or skip or retry or control"
```

Expected: FAIL on missing scheduler-control behavior.

- [ ] **Step 5: Add a retry integration test that proves requeue plus wake-up**

Cover:
- retry changes the node back to `ready`
- retry re-enters the ready path
- the scheduler can dispatch the retried node again

- [ ] **Step 6: Implement minimal scheduler hooks**

In `dag_scheduler.py`:
- check control state before dispatch
- support `pause_requested -> paused`
- support resume
- ignore stale completion/failure from skipped nodes
- expose a small recompute/wake path for retry

- [ ] **Step 7: Keep event vocabulary compatible**

Prefer existing `log`, `node_update`, and `dag_update` events for control visibility instead of inventing a new transport surface unless a failing test proves it is necessary.

- [ ] **Step 8: Run the scheduler and bridge tests**

Run the same command again and confirm PASS.

## Task 4: RED/GREEN for monitor-recovery snapshot persistence

**Files:**
- Modify: `backend/app/models/task_node.py`
- Modify: `backend/app/schemas/task.py`
- Modify: `backend/app/services/task_service.py`
- Modify: `backend/tests/test_task_api.py`
- Modify: `frontend/src/stores/taskStore.ts`
- Modify: `frontend/src/api/tasks.ts`

- [ ] **Step 1: Write failing API tests for enriched task detail fields**

Cover presence of:
- `nodes[].started_at`
- `nodes[].finished_at`
- `nodes[].assigned_agent`
- `checkpoint_data.control`
- `checkpoint_data.control.preview_cache`
- `checkpoint_data.control.review_scores`

- [ ] **Step 2: Run the API tests and confirm failure**

Run:
```bash
cd /root/github/agentic-nexus
backend/.venv/bin/python -m pytest -q backend/tests/test_task_api.py -k "task detail and control"
```

Expected: FAIL because the detail schema is too thin.

- [ ] **Step 3: Add failing backend persistence tests for preview and review-score caches**

Cover:
- after a chapter preview event is observed, a fresh `GET /api/tasks/{id}` can return the persisted preview cache
- after a review score event is observed, a fresh `GET /api/tasks/{id}` can return the persisted review score cache

- [ ] **Step 4: Implement durable preview and review-score persistence**

Use a small focused helper so monitor-recovery data writes are not spread across unrelated modules.

- [ ] **Step 5: Expand the task detail schema and service mapping**

Return monitor-recovery fields from `get_task_detail(...)`.

- [ ] **Step 6: Update frontend task typing**

Keep the `Task` shape aligned with the backend response used by monitor hydration.

- [ ] **Step 7: Re-run the task detail test lane**

Confirm PASS.

## Task 5: RED/GREEN for normalized monitor store and WebSocket reducers

**Files:**
- Modify: `frontend/src/stores/monitorStore.ts`
- Modify: `frontend/src/stores/__tests__/monitorStore.test.ts`
- Modify: `frontend/src/hooks/__tests__/useTaskWebSocket.test.ts`

- [ ] **Step 1: Write failing store tests for normalized monitor state**

Cover:
- hydrating node map from task snapshot
- ingesting `node_update`
- ingesting `agent_status`
- ingesting `chapter_preview`
- ingesting `review_score`
- ingesting `consistency_result`
- tracking `selectedNodeId`
- updating toolbar control state

- [ ] **Step 2: Write failing hook tests for resync behavior with enriched snapshot**

Cover:
- reconnect snapshot hydration restores normalized nodes and control state
- stale events are still ignored

- [ ] **Step 3: Run the frontend store/hook tests and confirm failure**

Run:
```bash
cd /root/github/agentic-nexus/frontend
npm run test -- monitorStore useTaskWebSocket
```

Expected: FAIL because the current store only keeps flat events.

- [ ] **Step 4: Implement normalized store reducers**

Keep reducers small:
- snapshot hydration
- event-specific ingestion
- selection
- optimistic pending command markers

- [ ] **Step 5: Run the store/hook tests**

Confirm PASS.

- [ ] **Step 6: Refactor helper functions**

Extract any node/status normalization helpers that become hard to read inline.

## Task 6: RED/GREEN for monitor components and page composition

**Files:**
- Create: `frontend/src/components/monitor/DagViewer.tsx`
- Create: `frontend/src/components/monitor/AgentPanel.tsx`
- Create: `frontend/src/components/monitor/LogStream.tsx`
- Create: `frontend/src/components/monitor/FsmProgress.tsx`
- Create: `frontend/src/components/monitor/ChapterPreview.tsx`
- Create: `frontend/src/components/monitor/ControlToolbar.tsx`
- Create: `frontend/src/components/monitor/__tests__/DagViewer.test.tsx`
- Create: `frontend/src/components/monitor/__tests__/ControlToolbar.test.tsx`
- Create: `frontend/src/components/monitor/__tests__/MonitorPage.test.tsx`
- Modify: `frontend/src/pages/Monitor.tsx`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Write failing component tests**

Cover:
- `DagViewer` maps node statuses to visual classes/labels and emits node selection
- `ControlToolbar` enables/disables buttons based on selected node and control state
- `Monitor` page renders the full control-tower structure

- [ ] **Step 2: Run the component tests and confirm failure**

Run:
```bash
cd /root/github/agentic-nexus/frontend
npm run test -- DagViewer ControlToolbar MonitorPage
```

Expected: FAIL because the components do not exist yet.

- [ ] **Step 3: Implement `FsmProgress`, `AgentPanel`, `LogStream`, and `ChapterPreview`**

Keep these components presentational and driven by store selectors.

- [ ] **Step 4: Render the consistency summary surface in the bottom row**

Ensure the monitor page exposes the latest `consistency_result` state alongside chapter preview content instead of dropping it in raw events only.

- [ ] **Step 5: Implement `ControlToolbar`**

Use the task control API helpers and store pending markers.

- [ ] **Step 6: Implement `DagViewer`**

Use G6 as a renderer only. React owns the selected node state and graph data derivation.

- [ ] **Step 7: Upgrade `Monitor.tsx` to the approved Control Tower layout**

Top row:
- FSM progress
- connection and task summary
- control toolbar

Main area:
- DAG left
- agent panel and logs right

Bottom:
- preview tabs, badges, and consistency summary

- [ ] **Step 8: Add CSS support for monitor layout and node state affordances**

Include:
- running glow/pulse
- stable panel layout
- narrow-screen fallback

- [ ] **Step 9: Run the component test lane**

Confirm PASS.

## Task 7: REFACTOR and integration verification

**Files:**
- Modify only files already touched in earlier tasks
- Modify: `.gitignore`
- Modify: `docs/progress.md`
- Modify: `docs/task_plan.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Add `.superpowers/` to `.gitignore`**

Avoid committing the brainstorming screen artifacts.

- [ ] **Step 2: Refactor duplicated helpers**

Possible targets:
- control metadata update helpers
- monitor event normalization helpers
- task detail response construction

- [ ] **Step 3: Run targeted backend verification**

Run:
```bash
cd /root/github/agentic-nexus
backend/.venv/bin/python -m pytest -q backend/tests/test_task_control.py backend/tests/test_task_api.py backend/tests/test_dag_scheduler.py backend/tests/test_event_bridge.py
```

Expected: PASS.

- [ ] **Step 4: Run targeted frontend verification**

Run:
```bash
cd /root/github/agentic-nexus/frontend
npm run test
npm run lint
```

Expected: PASS.

- [ ] **Step 5: Update project docs**

Record:
- Step 5.5 and 5.6 progress
- control API completion
- verification evidence

- [ ] **Step 6: Prepare Stage 3 review handoff**

Collect the exact changed file set and verification commands so code review and security review can audit from evidence rather than guesswork.
