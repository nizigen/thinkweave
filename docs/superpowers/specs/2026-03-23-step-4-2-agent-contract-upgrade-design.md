# Step 4.2 Agent Contract Upgrade Design

**Date:** 2026-03-23  
**Scope:** Long-text runtime specialized agents and memory integration  
**Status:** Approved design baseline for implementation

## Goal

Complete Step 4.2 by upgrading the current runtime-specialized agents so they follow explicit role contracts inspired by `academic-paper/agents`, while staying aligned with this system's existing long-text generation workflow.

This step does not import the full academic-paper pipeline into runtime. It strengthens the existing execution-layer agents:
- `OutlineAgent`
- `WriterAgent`
- `ReviewerAgent`
- `ConsistencyAgent`
- `MemoryMiddleware`

## Why This Design

The current platform is a task-orchestration runtime, not a full academic-writing assistant from intake through submission formatting. The document workflow in this repo is already fixed around:

`OUTLINE -> OUTLINE_REVIEW -> WRITING -> PRE_REVIEW_INTEGRITY -> REVIEWING -> CONSISTENCY -> FINAL_INTEGRITY -> DONE`

Because of that, the correct reference strategy is:
- reuse the **design style** of `academic-paper` agents;
- preserve the repo's existing runtime architecture and FSM boundaries;
- avoid expanding Step 4.2 into a new multi-phase 12-agent system.

## Reference Mapping

The following reference agents are the design source for this step:

| Runtime Agent | Primary Reference | Borrowed Patterns |
|---|---|---|
| `OutlineAgent` | `structure_architect_agent` | section blueprint, evidence allocation, explicit structure contracts |
| `OutlineAgent` | `argument_builder_agent` | claim ownership, boundaries, argument decomposition |
| `WriterAgent` | `draft_writer_agent` | section discipline, evidence-aware writing, transition requirements |
| `ReviewerAgent` | `peer_reviewer_agent` | rubric scoring, actionable fixes, verdict contract |
| `ReviewerAgent` | reviewer-family agents in `academic-paper-reviewer` | stronger challenge and critique framing |
| `ConsistencyAgent` | `academic-pipeline/integrity_verification_agent` | structured integrity issues, cross-section verification |
| `MemoryMiddleware` | whole academic-paper pipeline handoff model | explicit upstream/downstream context contracts |

The following reference agents are **not** pulled into Step 4.2 runtime execution:
- `intake_agent`
- `literature_strategist_agent`
- `revision_coach_agent`
- `citation_compliance_agent`
- `abstract_bilingual_agent`
- `formatter_agent`
- `visualization_agent`
- `socratic_mentor_agent`

Those remain future interactive or later-phase capabilities.

## Architecture Decision

### Keep current runtime shape

Step 4.2 remains a runtime execution enhancement on top of the current three-layer architecture:
- Layer 0: orchestrator
- Layer 1: manager
- Layer 2: specialized worker agents

### Strengthen contracts instead of adding more runtime roles

Current agents are too thin. They normalize payloads, but do not strongly express:
- what inputs they require;
- what structured outputs they must produce;
- what quality bar they enforce;
- what memory context they consume and emit.

Step 4.2 upgrades those contracts without changing the macro architecture.

## Target Runtime Contracts

### 1. `OutlineAgent`

**Purpose**
- Produce a chapter plan that is safe for parallel writing.
- Define chapter territory clearly enough to reduce duplication before drafting begins.

**Required input contract**
- `title`
- `mode`
- `target_words`
- optional `draft_text`
- optional `review_comments`
- optional `style_requirements`

**Required output responsibilities**
- chapter list with explicit ordering;
- chapter summaries;
- chapter key points;
- context bridges between adjacent chapters;
- `topic_claims` ownership map;
- chapter boundaries stating what each chapter must not cover;
- evidence plan placeholders for downstream writing.

**Design rule**
- Output must serve two consumers at once:
  - human review/editing in outline review;
  - machine-safe downstream parsing for writing/review/memory.

### 2. `WriterAgent`

**Purpose**
- Draft one chapter only, using the full outline, chapter-local scope, and memory-derived anti-overlap context.

**Required input contract**
- `chapter_index`
- `chapter_title`
- `full_outline`
- `chapter_description`
- `context_bridges`
- `memory_context`
- `topic_claims`
- `assigned_evidence`
- `target_words`

**Required behavior**
- write only within chapter territory;
- use evidence and argument points assigned to that chapter;
- preserve transitions with surrounding chapters;
- avoid known overlaps from memory context;
- produce chapter text that can be summarized and re-indexed by memory.

**Design rule**
- `memory_context` is not optional runtime decoration; it is part of the authoring contract.

### 3. `ReviewerAgent`

**Purpose**
- Evaluate one chapter with a structured rubric that can drive FSM decisions.

**Required input contract**
- `chapter_index`
- `chapter_title`
- `chapter_content`
- `chapter_description`
- `overlap_findings`
- optional `topic_claims`
- optional `assigned_evidence`

**Required output contract**
Strict JSON with:
- total `score`
- `accuracy_score`
- `coherence_score`
- `evidence_sufficiency_score`
- `boundary_compliance_score`
- `non_overlap_score`
- `must_fix`
- `strongest_counterargument`
- `feedback`
- `pass`

**Design rule**
- Reviewer output must be deterministic enough for code to consume, not just prose critique.

### 4. `ConsistencyAgent`

**Purpose**
- Detect cross-chapter issues at the document level using chapter summaries first and full text only as fallback support.

**Required input contract**
- `chapters_summary`
- `full_text`
- optional `topic_claims`
- optional `chapter_metadata`

**Required output contract**
Strict JSON with issue families separated:
- `style_conflicts`
- `claim_conflicts`
- `duplicate_coverage`
- `term_inconsistency`
- `transition_gaps`
- `repair_targets`
- `pass`

**Design rule**
- Consistency review is not line editing. It focuses on multi-chapter correctness and cohesion.

### 5. `MemoryMiddleware`

**Purpose**
- Inject role-specific session memory before execution.
- Persist role-specific memory artifacts after execution.

**Mandatory middleware order**
- `Logging -> TokenTracking -> Timeout -> ContextSummary -> Memory -> Agent`

**Before-task behavior by role**
- `outline`: initialize task namespace; inject prior task-scoped context if available.
- `writer`: inject prior chapter summaries, dedup hints, and territory constraints.
- `reviewer`: inject overlap clues and chapter-level scope context.
- `consistency`: inject summary bundle and canonical terminology context.

**After-task behavior by role**
- `outline`: persist outline summary and territory map.
- `writer`: persist chapter summary, used evidence, and chapter metadata.
- `reviewer`: persist review summary and overlap-relevant findings.
- `consistency`: persist cross-chapter issue summary for later integrity stages.

## Non-Goals

This step will not:
- add new FSM states;
- add the full academic-paper multi-agent pipeline to runtime;
- implement citation formatting, abstract generation, or formatting/export logic;
- redesign DAG scheduling;
- redesign knowledge-graph promotion logic from Step 4.4.

## Files Expected to Change

Core implementation files:
- `backend/app/agents/worker.py`
- `backend/app/agents/outline_agent.py`
- `backend/app/agents/writer_agent.py`
- `backend/app/agents/reviewer_agent.py`
- `backend/app/agents/consistency_agent.py`
- `backend/app/agents/middleware.py`
- `backend/app/memory/session.py`

Prompt contracts:
- `backend/prompts/outline/generate.md`
- `backend/prompts/writer/write_chapter.md`
- `backend/prompts/reviewer/review_chapter.md`
- `backend/prompts/consistency/check.md`

Primary test coverage:
- `backend/tests/test_specialized_agents.py`
- `backend/tests/test_memory_middleware.py`
- `backend/tests/test_agent_core.py`
- new contract-oriented tests as needed

## Acceptance Criteria

Step 4.2 is complete only if all of the following are true:

1. Specialized agents enforce explicit role-specific payload contracts.
2. Prompts express the upgraded contracts clearly and without mojibake.
3. `MemoryMiddleware` is present in the default middleware chain in the required order.
4. Writer path proves that non-empty memory context can affect prompt construction after prior writes.
5. Reviewer and consistency paths return structured outputs suitable for runtime decisions.
6. Targeted tests cover both role normalization and memory roundtrip behavior.
7. No unresolved code-review or security-review HIGH findings remain.

## Implementation Strategy

Use strict tri-plugin order:
1. TDD-first contract tests for specialized agents and middleware.
2. Minimal runtime implementation to satisfy contracts.
3. Prompt refactor to make role contracts explicit.
4. Regression pass on current Step 4.2 and memory-related suites.
5. Code review and security review before claiming completion.

## Review Note

The original brainstorming skill recommends a spec-review subagent loop. I am not dispatching a subagent here because this session does not include explicit delegation permission. I will instead use a manual review pass and then proceed to the implementation plan.
