---
phase: "04"
name: "web-visibility-and-e2e"
status: "discussed"
updated: "2026-04-26"
---

# Phase 4: Web Observability Alignment + E2E Validation - Context

## Domain Boundary
Align monitor-facing visibility with the stage-oriented DAG runtime and close the loop with executable E2E evidence.

In scope:
- Monitor/UI mapping to semantic stage + DAG node status
- Task detail observability fields for troubleshooting and progress tracking
- Real-environment E2E scripts and regression checks

Out of scope:
- New generation capabilities outside observability/e2e
- Major architecture rewrites for scheduler/FSM core logic

## Canonical Refs
- `frontend/src/pages/MonitorPage.jsx`
- `frontend/src/lib/apiBase.js`
- `backend/app/routers/ws.py`
- `backend/app/routers/tasks.py`
- `backend/app/services/task_service.py`
- `backend/app/schemas/ws_event.py`
- `scripts/playwright_cli_real_env.sh`

## Decisions

### D1. Stage-Aligned Observability (Locked)
Monitor and API outputs must expose stage-oriented semantics (`stage_code`, phase progression, blocking reason) while preserving DAG execution details for diagnosis.

### D2. Failure Transparency (Locked)
Non-terminal runs must return actionable diagnostic fields (`blocking_reason`, node/task status snapshots, retry/repair trace hints) rather than generic timeout-only errors.

### D3. E2E Evidence As Gate (Locked)
Phase completion requires both:
- deterministic backend/unit checks for ws/task contracts
- real-env script evidence for UI create -> monitor visibility -> terminal/diagnosable non-terminal behavior

## Alignment Notes
- Keep KonrunsGPT-inspired stage semantics as the user-facing monitoring language.
- Keep agentic-nexus style DAG execution graph as the runtime truth source.
- Web observability is an alignment layer between those two views.

## Deferred Ideas
- Rich DAG interaction redesign on monitor page (editing/graph authoring) is deferred.
- Multi-task comparative analytics dashboard is deferred.
