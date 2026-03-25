# Monitor Control Tower Design

## Goal

Upgrade the existing monitor page into a full real-time orchestration console that covers Phase 5 Step 5.5 and Step 5.6:

- live DAG visualization
- agent activity panel
- rolling log stream
- FSM progress display
- chapter preview with review badges
- real task controls for pause, skip, and retry

The monitor page must reuse the existing REST snapshot plus WebSocket event model instead of introducing a separate control channel.

## Scope

### In Scope

- Upgrade [`frontend/src/pages/Monitor.tsx`](/root/github/agentic-nexus/frontend/src/pages/Monitor.tsx) into the main monitoring screen
- Add monitor subcomponents for DAG, agent panel, logs, FSM progress, preview, and controls
- Extend frontend monitor state so it can reconstruct the current task view from REST plus incremental WebSocket events
- Add backend task control APIs for pause, skip, and retry
- Extend scheduler behavior so control commands affect dispatch safely
- Extend task detail responses as needed for monitor recovery after refresh/reconnect
- Preserve Step 5.4 reconnection behavior and snapshot re-sync

### Out of Scope

- Replacing the existing WebSocket transport model
- Implementing DAG editing from the monitor page
- Adding a new dedicated monitor route or splitting Monitor into a separate page identity
- Hard-stop cancellation of already running agent work
- Broad task history or result-page redesign

## Current State

### Frontend

- [`frontend/src/pages/Monitor.tsx`](/root/github/agentic-nexus/frontend/src/pages/Monitor.tsx) currently only shows connection state, reconnect count, and last error
- [`frontend/src/hooks/useTaskWebSocket.ts`](/root/github/agentic-nexus/frontend/src/hooks/useTaskWebSocket.ts) already handles:
  - auth subprotocol handshake
  - exponential reconnect
  - stale socket protection
  - reconnect snapshot sync through `getTask(taskId)`
- [`frontend/src/stores/monitorStore.ts`](/root/github/agentic-nexus/frontend/src/stores/monitorStore.ts) currently stores only connection state, task snapshot, and a flat retained event list

### Backend

- [`backend/app/routers/tasks.py`](/root/github/agentic-nexus/backend/app/routers/tasks.py) supports list and detail reads, but not task control commands
- [`backend/app/services/dag_scheduler.py`](/root/github/agentic-nexus/backend/app/services/dag_scheduler.py) owns node dispatch, retries, completion, and failure transitions
- [`backend/app/schemas/ws_event.py`](/root/github/agentic-nexus/backend/app/schemas/ws_event.py) already defines the monitoring event types needed by the page
- [`backend/app/models/task.py`](/root/github/agentic-nexus/backend/app/models/task.py) already provides `checkpoint_data`, which is the preferred place to persist task-level control metadata

## Chosen Approach

Use an incremental extension of the existing monitoring pipeline:

1. Keep `/monitor/:taskId` as the only monitor route
2. Keep REST task detail as the recovery source of truth
3. Keep WebSocket as the incremental event stream
4. Add task control as explicit REST APIs
5. Keep the scheduler as the only actor allowed to make execution-state decisions

Rejected alternatives:

- pure WebSocket control channel: weaker recovery semantics after refresh and not aligned with current backend contracts
- frontend-driven node state mutation: would split execution truth across UI and scheduler

## UX Layout

Use the approved "Control Tower" layout:

- top row:
  - FSM progress
  - connection/task summary
  - control toolbar
- main body:
  - left: live DAG viewer
  - right top: agent activity panel
  - right bottom: log stream
- bottom row:
  - chapter preview tabs
  - review score badges
  - consistency summary

This layout keeps the DAG as the main visual surface while leaving control actions near task-level state.

## Frontend Design

### Page Structure

Upgrade [`frontend/src/pages/Monitor.tsx`](/root/github/agentic-nexus/frontend/src/pages/Monitor.tsx) into a composition page that renders:

- `FsmProgress`
- `ControlToolbar`
- `DagViewer`
- `AgentPanel`
- `LogStream`
- `ChapterPreview`

The page itself should not parse raw events directly.

### New Component Boundaries

Create these components under `frontend/src/components/monitor/`:

- `DagViewer.tsx`
- `AgentPanel.tsx`
- `LogStream.tsx`
- `FsmProgress.tsx`
- `ChapterPreview.tsx`
- `ControlToolbar.tsx`

Responsibilities:

- `DagViewer`: render normalized nodes and edges through `@antv/g6`, emit selected node changes
- `AgentPanel`: show active agents, current role/task assignment, and recent execution summary
- `LogStream`: render retained logs with auto-scroll and pause toggle
- `FsmProgress`: display current FSM stage progression and terminal state
- `ChapterPreview`: render markdown preview grouped by node or chapter and attach score badges
- `ControlToolbar`: surface pause, skip, and retry actions with optimistic pending-state feedback

### Frontend State Model

Evolve [`frontend/src/stores/monitorStore.ts`](/root/github/agentic-nexus/frontend/src/stores/monitorStore.ts) into the monitor truth store.

Required state:

- `activeTaskId`
- `taskSnapshot`
- `fsmState`
- `nodesById`
- `nodeOrder`
- `selectedNodeId`
- `agentActivityById`
- `logs`
- `chapterPreviewByNodeId`
- `reviewScoresByNodeId`
- `consistencySummary`
- `controlState`
- retained `events` for debugging only

Required actions:

- snapshot hydration from `getTask(taskId)`
- event-specific reducers for `connected`, `node_update`, `agent_status`, `log`, `chapter_preview`, `review_score`, `consistency_result`, `dag_update`, `task_done`
- node selection
- control command pending/success/failure markers

### Data Hydration Rules

- initial load and reconnect must hydrate from REST snapshot first
- subsequent WebSocket events apply incremental updates
- stale or cross-task events must be ignored
- graph rendering data should be derived from normalized store state, not stored independently inside the G6 instance

### Control UX Rules

- the left-most control slot is stateful:
  - `暂停执行` when task status is `pending` or `running` and control state is not paused
  - `继续执行` when task control state is `paused`
- `skip` requires a selected node and only enables for `pending`, `ready`, or `running`
- `retry` requires a selected node and only enables for `failed` or `skipped`
- toolbar actions show pending state immediately, but final UI truth comes from REST response plus later events

## Backend Design

### New API Surface

Add task control endpoints under [`backend/app/routers/tasks.py`](/root/github/agentic-nexus/backend/app/routers/tasks.py):

- `POST /api/tasks/{task_id}/control/pause`
- `POST /api/tasks/{task_id}/control/resume`
- `POST /api/tasks/{task_id}/control/skip`
- `POST /api/tasks/{task_id}/control/retry`

Each endpoint must:

- require the same task visibility/auth model as task detail
- validate command legality against current task/node state
- call a dedicated task control service instead of mutating ORM state in the router
- return the latest task detail snapshot needed by the monitor page

Request shapes:

- `pause` and `resume`: empty JSON body
- `skip`: JSON body with required `node_id`
- `retry`: JSON body with required `node_id`

### Task Control Service

Create a dedicated service, expected at [`backend/app/services/task_control.py`](/root/github/agentic-nexus/backend/app/services/task_control.py), to own:

- command validation
- task/node state mutation
- `checkpoint_data.control` persistence
- scheduler wake-up integration
- monitoring event emission

This avoids spreading execution-control rules across router, scheduler, and page code.

### Control Persistence Contract

Persist task-level control data under `tasks.checkpoint_data["control"]`.

Expected shape:

```json
{
  "status": "active|pause_requested|paused",
  "pause_requested_at": "ISO timestamp or null",
  "last_command": {
    "type": "pause|resume|skip|retry",
    "node_id": "uuid or null",
    "issued_at": "ISO timestamp"
  },
  "preview_cache": {},
  "review_scores": {}
}
```

Optional per-node command bookkeeping may also live in `checkpoint_data`, but persistent task truth must remain derivable from the task row plus task nodes.

### Scheduler Semantics

Update [`backend/app/services/dag_scheduler.py`](/root/github/agentic-nexus/backend/app/services/dag_scheduler.py) with minimal cooperative control hooks:

- before dispatching ready nodes, check whether the task is `pause_requested` or `paused`
- when pause is acknowledged, stop assigning new nodes and emit a monitor-visible state change
- if a running node has been skipped, ignore any later completion payload from that node
- expose a small wake/recompute entrypoint for control commands

The main scheduler loop should not be rewritten.

### Command Semantics

#### Pause

- allowed when task is `pending` or `running`
- does not terminate in-flight agent work
- prevents any further node dispatch after current running work settles
- transitions the task into a durable paused control state

#### Resume

- allowed when task control state is `paused`
- clears the paused control state
- re-enables normal dispatch without mutating node terminal states
- uses the same toolbar slot as pause on the frontend

#### Skip

- requires `node_id`
- allowed for nodes in `pending`, `ready`, or `running`
- marks the node as `skipped`
- if the node was running, later completion/failure callbacks from that node must be ignored as stale
- recomputes downstream readiness based on the skipped node being treated as terminal

#### Retry

- requires `node_id`
- allowed for nodes in `failed` or `skipped`
- resets node execution fields needed to safely re-enter scheduling
- requeues the node into the ready path

## Snapshot Contract Changes

Extend the task detail payload returned by `GET /api/tasks/{id}` so the monitor page can rebuild state after refresh.

Minimum additions:

- task-level:
  - `checkpoint_data.control`
  - `checkpoint_data.control.preview_cache`
  - `checkpoint_data.control.review_scores`
- node-level:
  - `started_at`
  - `finished_at`
  - `assigned_agent`

The monitor reconnect goal requires preview and score state to survive refresh. The backend must therefore either:

- persist preview and review-score caches inside `checkpoint_data.control`, or
- expose an equivalent durable snapshot in `GET /api/tasks/{id}`

Incremental-only preview or score state is not sufficient for this implementation.

## WebSocket/Event Handling

No new transport is required. Reuse current event families:

- `connected`
- `node_update`
- `agent_status`
- `log`
- `chapter_preview`
- `review_score`
- `consistency_result`
- `dag_update`
- `task_done`

Control commands should result in visible follow-up events, typically through `log` and `dag_update`, so secondary clients stay in sync.

## Monitor Data Source Table

| Monitor Surface | Primary Snapshot Source | Incremental Event Source | Must Survive Reconnect |
|---|---|---|---|
| FSM progress | `task.fsm_state` | `dag_update`, `task_done` | Yes |
| DAG graph nodes | `task.nodes[]` | `node_update`, `dag_update` | Yes |
| Selected node detail | `task.nodes[]` | `node_update`, `dag_update` | Yes |
| Agent activity panel | durable task/node assignment fields | `agent_status`, `node_update` | Yes |
| Log stream | optional retained recent logs in task snapshot if available | `log`, control follow-up logs | No |
| Chapter preview | `checkpoint_data.control.preview_cache` or equivalent durable field | `chapter_preview` | Yes |
| Review badges | `checkpoint_data.control.review_scores` or equivalent durable field | `review_score` | Yes |
| Consistency summary | durable task snapshot field if present | `consistency_result` | No for first cut |
| Control toolbar state | `checkpoint_data.control` | `dag_update`, `log`, command response snapshot | Yes |

## Error Handling

### Frontend

- missing or stale task auth token keeps the current Step 5.4 failure behavior
- invalid control action shows an error and clears pending control state
- graph render failures should degrade to a task-node list fallback rather than blanking the page

### Backend

- illegal command-state combinations return 409
- task or node visibility failures return 404 under the existing auth model
- scheduler-control races must resolve in favor of persisted task/node state, not in-flight callback order

## Testing Strategy

### Frontend Tests

- store reducers for monitor event ingestion and snapshot hydration
- hook tests for reconnect plus resync behavior
- toolbar tests for command enable/disable rules and API integration
- DAG viewer tests for status mapping and node selection
- page-level tests for major monitor layout states

### Backend Tests

- router tests for auth, visibility, 404, 409, and happy path control commands
- service tests for pause, skip, and retry legality and persistence
- scheduler tests for:
  - pause halting new dispatch
  - resume re-enabling dispatch
  - skipped running node completion being ignored
  - retry requeue behavior
- event bridge tests confirming control-driven events are broadcast

### Verification

Targeted verification after implementation must include:

- backend task control tests
- backend scheduler regression subset
- backend event bridge/WebSocket regression subset
- frontend monitor store/hook/component tests
- frontend lint

## Risks and Constraints

### Primary Risk

`running` plus `skip` is the highest-risk path because completion callbacks may arrive after the operator already marked the node as skipped. Persistent node state must win over callback order.

### Secondary Risk

Monitor refresh/reconnect will produce inconsistent UI if the detail payload is not expanded enough to reconstruct control state and node timing.

### Constraint

The page must preserve the current Step 5.4 recovery strategy and should not replace it with a parallel real-time state channel.

## Implementation Order

1. backend control API tests
2. backend control service implementation
3. scheduler cooperative control hooks
4. task detail snapshot expansion
5. frontend monitor store upgrade
6. frontend monitor components and page composition
7. toolbar integration
8. backend plus frontend verification
9. code review and security review after Stage 2 evidence exists

## Acceptance Criteria

- `/monitor/:taskId` renders a real DAG, not just connection metadata
- node status changes appear in the graph within the current WebSocket update flow
- the page shows agent activity, log stream, FSM progress, and preview data in one screen
- refresh or reconnect restores the monitor without corrupting task state
- pause stops future dispatch without killing the currently running node
- resume continues dispatch after a paused task is released
- skip and retry behave predictably and survive refresh
- no execution truth is owned solely by the browser
