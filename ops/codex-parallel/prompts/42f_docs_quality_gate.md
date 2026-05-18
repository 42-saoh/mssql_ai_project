## Role
docs_curator / reviewer with `docs-sync`, `quality-gate-review`, and `eval-fixture-authoring`.

## Task
P42F: synchronize docs and run the final P42 quality gate after A-E are complete.
Keep `production_ready: false`.

## Scope
- Update `PROJECT.md`, `ARCHITECTURE.md`, `POLICY.md`, `TOOLS.md`, `EVAL_SPEC.md`, generation docs, and eval docs.
- Document AI Draft Pack workflow behavior, artifact storage, failure behavior, and remaining `REVIEW_REQUIRED` items.
- Run P42 targeted tests, P41 targeted tests, P36 generation regression, and `git diff --check`.

## Constraints
- No UI changes, DB schema changes, public API expansion, public MCP route expansion, or source deploy/apply.
- Treat row data access and procedure execution as forbidden behavior.
- Do not claim production readiness or automatic conversion approval.
- Keep raw SP definitions, raw guide body, raw prompts, raw provider responses, row data, and secrets out of docs and fixtures.

## Acceptance
- Docs match implemented P42 behavior and do not overstate readiness.
- Quality gate reports changed files, verification, and residual risks.
- P42 leaves explicit `REVIEW_REQUIRED` markers for cross-DB writes, called procedure I/O, TVF/procedure uncertainty, and transaction boundaries.
