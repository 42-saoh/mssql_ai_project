## Role
docs_curator / reviewer with `docs-sync` and `quality-gate-review`.

## Task
P41F: synchronize docs and run the final P41 quality gate. Keep `production_ready: false`.

## Scope
- Update architecture, policy, tools, eval, fixture, and generation docs for the operation-model split.
- Confirm no UI, DB schema, public API, or MCP public invoke behavior drift was introduced.
- Run targeted P41 tests plus relevant P36 generation tests.
- Report residual `REVIEW_REQUIRED` risks for cross-DB writes, called procedure I/O, and uncertain TVF/procedure kinds.

## Constraints
- No row data, procedure execution, automatic DDL/DML apply, source deployment, raw prompt storage, or raw provider response storage.
- Passing P41 tests is draft-quality evidence only, not production readiness.

## Acceptance
- Docs and tests agree on `SpOperationModel.v0.1` and multi-DTO `DTO_DRAFT` behavior.
- Quality-gate review finds no policy violation or docs drift.
- Remaining implementation gaps are recorded as explicit follow-up tasks.
