# P36E Output Renewal Docs Readiness

## Role

docs_curator + reviewer stance

## Context

Use the completed P36A-P36D changes and repository docs as source context.

## Task

Synchronize docs, fixtures, evals, and readiness notes after P36:

- API workflow notes
- Web display/download behavior
- validation rules
- golden/eval fixtures
- `PROJECT.md`, `ARCHITECTURE.md`, `POLICY.md`, `EVAL_SPEC.md`, `TOOLS.md`, and other relevant docs

## Constraints

- Preserve `production_ready: false`.
- Do not claim automatic conversion, deployment, or DDL application.
- Keep row-data/procedure-execution prohibitions visible.

## Acceptance

- Documentation and code contracts do not contradict each other.
- Quality gate reports remaining risks and TODOs.
