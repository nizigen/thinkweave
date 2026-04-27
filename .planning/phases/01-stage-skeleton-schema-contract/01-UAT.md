---
status: testing
phase: 01-stage-skeleton-schema-contract
source:
  - 01-01-SUMMARY.md
  - 01-02-SUMMARY.md
  - 01-03-SUMMARY.md
started: "2026-04-26T10:35:07+08:00"
updated: "2026-04-26T10:46:00+08:00"
---

## Current Test

number: 6
name: Failure Transparency Snapshot
expected: |
  Task detail exposes status/fsm/word_count/error_message and node distribution fields.
awaiting: completed

## Tests

### 1. Stage Metadata Injection
expected: Task creation path contains semantic pipeline metadata and DAG-preserved execution graph.
result: pass
notes: Verified by backend tests and phase summary evidence.

### 2. Schema Gate And Structured Repair
expected: reviewer/consistency output is schema-gated and invalid outputs trigger repair path.
result: pass
notes: Verified by test suite including agent core and scheduler.

### 3. Orphan Running Recovery
expected: stale running nodes are recovered to ready and re-enqueued.
result: pass
notes: Verified by TestOrphanRunningRecovery automated test.

### 4. UI Task Creation Path
expected: In UI flow, filling title and clicking create starts a new task.
result: pass
notes: Fixed API base + Authorization header injection; real-env script now shows API ASSERTION PASSED from UI flow without fallback.

### 5. E2E Terminal Convergence
expected: Real-env scripted run reaches terminal status (done/completed/failed) within configured timeout window.
result: issue
reported: "Task can remain non-terminal in short timeout windows; now API exposes blocking_reason for explicit non-terminal diagnosis"
severity: major

### 6. Failure Transparency Snapshot
expected: Task detail response includes status/fsm_state/word_count/error_message plus node/routing visibility.
result: pass
notes: Verified from script output task summaries.

## Summary

total: 6
passed: 5
issues: 1
pending: 0
skipped: 0

## Gaps

### GAP-02 Terminal Convergence Stability
severity: major
affects:
  - runtime scheduling / agent throughput / convergence timing
  - timeout-window observability
observed_in:
  - real-env script runs with timeout (120s, 180s)
symptom: task can remain pending before timeout despite partial node progression; blocking_reason now available from `/api/tasks/{id}` and script output.
acceptance_fix:
  - task reaches terminal state within agreed timeout, OR
  - timeout run emits explicit `TERMINAL_BLOCKING_REASON` based on API `blocking_reason` (implemented).
