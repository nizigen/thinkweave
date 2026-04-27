# ThinkWeave REQUIREMENTS

## R1 Stage Contracts
- Define semantic stage contracts and role mapping.
- Inject `stage_code`, `schema_version`, `stage_contract` into DAG payloads.

## R2 Pipeline Rewrite
- Implement research-first flow:
  Research -> Outline -> Section Writer -> Reviewer -> Consistency.

## R3 Repair And Quality
- Add targeted repair DAG from consistency failures.
- Add final polish and quality gates for structure/evidence/length/conflicts.

## R4 Observability
- Keep monitor behavior aligned with new stage semantics.
- Expose failure reasons, retry traces, repair waves.
