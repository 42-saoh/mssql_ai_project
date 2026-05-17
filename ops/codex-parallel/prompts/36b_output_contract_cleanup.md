# P36B Output Contract Cleanup

## Role

platform_worker

## Context

Use `spec/eval/p36_output_renewal_contract.yaml` and `tasks/0036-output-renewal.md` as the source of truth.

## Task

Hard-remove retired outputs from public request, API, UI, validation, mapping, and generation contracts:

- requested output types: `DTO_MODEL_DRAFT`, `DDL_DRAFT`
- artifact types: `VO_DRAFT`, `MODEL_DRAFT`, `DDL_DRAFT`

Add a manual-apply `db/schema/` v9 SQL file for artifact type CHECK constraint renewal. Do not apply it automatically.

## Constraints

- Keep `TABLE_COLUMN_METADATA` behavior if still present for existing workflow support.
- Do not mutate business databases.
- Do not auto-run DDL.
- Preserve existing migrations; add a new manual SQL artifact only.

## Acceptance

- OpenAPI/domain/web/validation tests agree on the final artifact contract.
- Removed names are absent from public request/output selections.
- v9 SQL is present and documented as manual review/apply only.
