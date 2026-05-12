# P29B Remaining Risks Follow-up Prompt

PROJECT.md, AGENTS.md, ARCHITECTURE.md, TOOLS.md, POLICY.md, EVAL_SPEC.md,
and TASK_TEMPLATE.md are the baseline for this task.

## Role

- Primary: platform_worker
- Secondary when needed: reviewer, docs_curator

## Preferred Skills

- contract-to-code
- quality-gate-review
- docs-sync

## Context

P29 Web Diagnostic UI + Workflow Evidence Wiring has already been implemented.

Implemented state:

- Web route `/metadata/dependencies` exists and uses the P28 safe invoke API.
- `PortalApi` / HTTP client / Web types include metadata tools summary and safe
  invoke support.
- Workflow automatically calls only `get_dependency_closure` for PROCEDURE
  targets.
- Workflow stores only a sanitized `dependencyEvidence` digest and merges
  dependency evidence refs into generation context and draft artifact evidence.
- `resolve_dependency_reference` remains manual-only in the Web diagnostic UI.
- P29 selected pytest suite passed through the Windows helper and `make`.
- `make test-web-smoke` passed.
- `git diff --check` passed with CRLF normalization warnings only.

Known remaining risks and TODO:

1. New DB migration was not created.
2. New persisted artifact type was not created.
3. Workflow state transition changes were not created.
4. Live PPM hard gate remains explicit-env-only and was not part of the P29
   default verification.
5. `.codex/config.toml` is dirty but appears to be environment/workspace config
   drift, not part of P29.

## Task

Continue from P29 and handle the remaining risks/TODO safely as P29B.

Start by inspecting the current repo state:

- `git -c safe.directory=D:/wt/p23 -C D:/wt/p23 status --short`
- Review P29 changes before editing.
- Treat `.codex/config.toml` as unrelated unless it is explicitly needed for
  this task.

Decide the smallest safe P29B slice:

- Prefer confirming and documenting deferred boundaries over creating new
  platform storage shape.
- Do not add DB migration, a persisted artifact type, or workflow state
  transition changes unless a current contract clearly requires it and focused
  tests can cover it.
- If those items remain deferred, make the deferred boundary explicit and
  consistent across contracts, docs, and tests.
- If live PPM prerequisites are available, run the explicit hard-live gate.
- If live PPM prerequisites are unavailable, do not fake the gate and do not
  weaken the blocker semantics. Report the exact unavailable prerequisite.

## In Scope

- Repo state inspection and dirty-file classification.
- Contract/docs/test hardening for the P29B deferred boundary.
- Verification of PPM hard-live gate only when the explicit live environment is
  genuinely available.
- Clear reporting of whether DB migration, persisted artifact type, and workflow
  state transitions remain deferred.
- `.codex/config.toml` status recommendation without reverting unrelated user or
  environment changes.

## Out of Scope

- Automatic DB schema application.
- New DB migration unless the current contract requires it.
- New persisted artifact type unless the current contract requires it.
- New workflow state transitions unless the current contract requires them.
- Row data access.
- Procedure execution.
- Free-form SQL.
- Business DB DDL/DML.
- Raw SP definition, raw prompt, or raw provider response storage.
- PPM-to-PLF fallback.
- Reverting unrelated dirty worktree changes.

## Target Files/Dirs

Inspect first, then edit only if needed:

- `spec/eval/p27_dependency_evidence_tooling_contract.yaml`
- `ARCHITECTURE.md`
- `TOOLS.md`
- `EVAL_SPEC.md`
- `apps/api/README.md`
- `apps/web/README.md`
- `services/mssql-mcp/README.md`
- `docs/integration-eval-status.md`
- `tests/contract/**`
- `tests/eval/**`
- `tests/unit/**`
- `tests/integration/**`

Treat as likely unrelated:

- `.codex/config.toml`

## Constraints

- Preserve the MCP registry boundary for MSSQL metadata access.
- Preserve the P28 safe invocation API contract.
- Preserve P29 workflow behavior: only `get_dependency_closure` is automatic.
- Preserve manual-only behavior for `resolve_dependency_reference`.
- Preserve sanitized `dependencyEvidence` only; do not store raw definitions,
  raw prompts, raw provider responses, row data, or SQL text.
- Preserve `dbProfileId=ppm` blocker behavior when PPM is unavailable; never
  fall back to PLF.
- In Windows PowerShell, run Makefile targets through:
  `powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 ...`

## Verification

Default fixture-first verification:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 make test PYTEST_ARGS="tests/unit/test_mcp_catalog.py tests/unit/mcp/test_tool_registry.py tests/contract/mcp/test_tool_invocation_contract.py tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py tests/unit/api/test_metadata_service.py tests/unit/api/test_metadata_gateway.py tests/unit/api/test_workflow_service.py tests/unit/api/test_route_surface.py tests/unit/web/test_p14_product_ui_static.py tests/integration/api/test_api_workflow_routes.py tests/e2e/test_fixture_workflow_happy_path.py tests/contract/test_openapi_and_env_sample_assets.py"
```

Web smoke:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 make test-web-smoke
```

Diff check:

```powershell
git -c safe.directory=D:/wt/p23 -C D:/wt/p23 diff --check
```

Optional explicit live PPM hard gate, only if live env is available:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 env P27_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/eval/test_p27_dependency_evidence_hard_live_gate.py"
```

If the live gate cannot be run, report that as an explicit unavailable
prerequisite. Do not replace it with fixture evidence.

## Done Definition

- Repo dirty state is inspected and classified.
- DB migration status is explicit: created with tests, or still deferred with
  docs/contracts/tests aligned.
- Persisted artifact type status is explicit: created with tests, or still
  deferred with docs/contracts/tests aligned.
- Workflow state transition status is explicit: changed with tests, or still
  deferred with docs/contracts/tests aligned.
- Live PPM hard gate result is recorded, or the unavailable prerequisite is
  recorded without faking evidence.
- `.codex/config.toml` is reported separately and not reverted unless explicitly
  requested.
- Relevant fixture-first tests pass.
- `make test-web-smoke` passes if Web files or Web docs/tests changed.
- `git diff --check` passes.

## Report Format

Use this format in the final response:

- Changed files
- What changed
- Deferred decisions:
  - DB migration
  - persisted artifact type
  - workflow state transition
- Live PPM hard gate result or unavailable prerequisite
- `.codex/config.toml` status and recommendation
- Verification commands and results
- Remaining risks
