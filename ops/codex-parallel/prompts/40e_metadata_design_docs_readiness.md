## Role

docs_curator with docs-sync, quality-gate-review, and eval-fixture-authoring.

## Task

Synchronize docs and readiness notes for P40 natural-language metadata design
chat.

## Constraints

- Keep `production_ready: false`.
- Reiterate no DDL/DML/procedure execution, no auto apply/deploy, no row data,
  and no workflow artifact persistence.
- State that `designInputs.fields` remains API-compatible but Web hides field
  rows.

## Acceptance

- PROJECT, ARCHITECTURE, API/Web READMEs, and eval docs mention P40 behavior.
- P38/P36 guardrails remain intact.
- Final gates and remaining risks are reported.
