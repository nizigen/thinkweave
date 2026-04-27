---
phase: "05"
name: "ultimate-longform-30k-closure"
status: "discussed"
updated: "2026-04-27"
---

# Phase 5: Ultimate Longform 30k Closure - Context

## Domain Boundary

Build a production-ready longform pipeline that can reliably generate >=30,000-word outputs with auditable evidence, stable cross-chapter consistency, and repeatable evaluation gates.

In scope:
- Research execution upgrade (tool-backed evidence collection, not plan-only JSON)
- 30k-aware planning and adaptive word budget control
- Assembly rewrite and robust consistency-repair policy
- Longform benchmark/e2e acceptance for >=30k targets

Out of scope:
- Frontend visual redesign unrelated to longform quality gates
- Replacing DAG runtime (keep agentic-nexus DAG as execution truth)

## Canonical Refs (Current Project)
- `backend/app/services/task_decomposer.py`
- `backend/app/services/dag_scheduler.py`
- `backend/app/services/long_text_fsm.py`
- `backend/app/agents/worker.py`
- `backend/app/agents/researcher_agent.py`
- `backend/app/prompts/*`
- `scripts/playwright_cli_real_env.sh`

## External Open-Source Integration Map

### R1. GPT-Researcher (multi-agent research-to-report)
- Repo: `assafelovic/gpt-researcher`
- Reference paths:
  - `multi_agents/agents/orchestrator.py`
  - `multi_agents/agents/writer.py`
  - `gpt_researcher/prompts.py`
- Reusable patterns:
  - explicit orchestration across research/writing roles
  - source-grounded report generation flow and observability
- Integration target in ThinkWeave:
  - `worker.py` researcher execution mode
  - research/evidence prompt+schema contracts
  - task checkpoint evidence trace fields

### R2. Open Deep Research (LangChain)
- Repo: `langchain-ai/open_deep_research`
- Reference paths:
  - `src/open_deep_research/prompts.py`
  - `src/legacy/tests/test_report_quality.py`
- Reusable patterns:
  - research prompt structure for tool-backed retrieval
  - report-quality testing harness patterns
- Integration target in ThinkWeave:
  - longform eval harness (`tests/` + scripts)
  - prompt and quality gate contracts

### R3. STORM (Stanford)
- Ref: `storm-project.stanford.edu/research/storm/`
- Reusable pattern:
  - pre-writing quality as first-class predictor of final article quality
- Integration target in ThinkWeave:
  - strengthen research+outline gate before writing fanout

### R4. LongWriter / LongGenBench
- Refs:
  - `arxiv.org/abs/2408.07055`
  - `openreview.net/pdf?id=3A71qNKWAS`
- Reusable patterns:
  - long output requires explicit decomposition + longform-aware evaluation
  - instruction adherence degrades with long generation; must benchmark at target length buckets
- Integration target in ThinkWeave:
  - >=30k evaluation tracks and pass thresholds

## Locked Decisions

### D1. Keep DAG Runtime, Upgrade Data Contracts
DAG remains execution truth. All improvements are additive in planning/contracts/gates, not a runtime rewrite.

### D2. 30k Is A Hard Product Gate
For longform mode, success requires final word_count >= target_words and passing evidence + consistency acceptance checks.

### D3. Tool-Backed Research Is Mandatory For Report Mode
For `mode=report`, researcher stage must perform retrieval/tool execution and persist citation-ready evidence ledger.

### D4. Assembly Is A Dedicated Stage, Not Join-Only
`finalize_output` join is insufficient for 30k quality; add explicit assembly rewrite stage and then re-check consistency.

## Gap Summary (from code audit)
- Researcher currently runs chat-only flow (`worker.py`) and does not execute `chat_with_tools`.
- Chapter count is depth-bounded (`quick/standard/deep`) rather than target_words-adaptive for 30k.
- Final output assembly is join-by-title in `long_text_fsm.finalize_output`.
- Consistency repair has fixed retry/wave budgets and can exhaust before convergence.
- Existing e2e script defaults to quick+1200-word smoke, not 30k regression.
