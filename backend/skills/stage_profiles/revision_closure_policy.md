---
name: revision_closure_policy
type: agent_behavior
applicable_roles: [writer]
applicable_modes: [all]
applicable_stages: [writing, re_revise, revise]
priority: 20
description: Force traceable closure log for revisions.
---
- For each review issue, produce issue-action-evidence closure items.
- Avoid scope drift and avoid introducing duplicated cross-chapter content.
- Keep unresolved items explicit with status=partial or not_fixed.
