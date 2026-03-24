---
name: reviewer_gate_policy
type: agent_behavior
applicable_roles: [reviewer]
applicable_modes: [all]
applicable_stages: [reviewing, re_review]
priority: 10
description: Enforce rubric + must-fix gate policy during review stages.
---
- Apply strict rubric scoring and keep decisions consistent across chapters.
- Mark pass only when no blocking issue remains.
- Always provide strongest counterargument for major claims.
