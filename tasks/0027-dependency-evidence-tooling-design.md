# P27 Dependency Evidence Tooling

## Status

- phase: P27
- status: fixture_first_hardened_with_explicit_live_gate
- production_ready: false

## Goal

Strengthen the deterministic dependency evidence layer that supports AI-heavy
stored procedure analysis. This slice hardens `get_dependency_closure` and
`resolve_dependency_reference` as active read-only MCP tools with fixture-first
behavior, mocked live repository coverage, and an explicit P27 hard-live gate,
without adding dedicated API invocation routes, Web UI, workflow wiring, DB
schema changes, or persisted artifact types.

## Scope

- Keep the `get_procedure_dependencies` contract extended with optional
  resolution evidence fields:
  - `resolutionConfidence`
  - `resolutionEvidenceKind`
  - `unresolvedReason`
  - `resolutionChain`
- Implement two active, read-only, structured-input MCP tools:
  - `get_dependency_closure`
  - `resolve_dependency_reference`
- Expose the tools only through the existing safe API metadata tool summary.
- Add `P27_HARD_LIVE_GATE=1` as an explicit opt-in hard-live PPM evidence gate.
- Keep LLM/P24 dependency input as a dependency evidence digest, not raw SQL.
- Preserve `production_ready: false`.

## Out Of Scope

- Dedicated API invocation endpoint.
- Web UI wiring.
- Runtime workflow changes.
- Persisted artifact type changes.
- Default live metadata, live OpenAI, or live PPM gate requirements.
- Row data, procedure execution, business DB DDL/DML, raw prompt storage, raw SP
  definition storage, or raw provider response storage.

## Contract Decisions

`get_dependency_closure` accepts `dbProfileId`, `schema`, `objectName`,
`objectType`, `maxDepth`, and `includeReviewRequired`. `maxDepth` defaults to
`2` and has a validator-enforced hard maximum of `3`. Its output is
`rootObject`, `nodes`, `edges`, `unresolved`, and `summary`; each edge carries
dependency type, resolution status/strategy, resolution evidence metadata, and
evidence refs. TABLE dependencies are leaf nodes, while confirmed
PROCEDURE/VIEW/FUNCTION dependencies may be expanded.

`resolve_dependency_reference` accepts a structured source object plus optional
referenced server/database/schema and required referenced name. Its output is
candidates, a selected resolution only when the full candidate set has exactly
one catalog-confirmed high-confidence target, resolution status/strategy,
evidence refs, and caveats.

The explicit P27 hard-live gate uses `selected_objects.yaml` as read-only live
target evidence. When `P27_HARD_LIVE_GATE=1` and
`MSSQL_ENABLE_LIVE_METADATA=1`, the gate validates selected simple/medium/complex
PPM procedures with bounded dependency closure and reference resolution. Missing
PPM profile/env, template-only manifest state, inaccessible PPM, or PLF fallback
is a blocker failure.
Local host-run live validation may set `MSSQL_METADATA_TDS_VERSION=7.0` when a
legacy/Chakra gateway rejects the default `python-tds` 7.4 negotiation.

Confirmed dependencies can feed downstream analysis as deterministic facts only
when catalog evidence is unique and high-confidence. Ambiguous names, unresolved
synonym targets, dynamic SQL markers, cross-server references without catalog
confirmation, and caller-dependent references remain `REVIEW_REQUIRED`.

## Verification

- `make test PYTEST_ARGS="tests/unit/test_mcp_catalog.py tests/unit/mcp/test_tool_registry.py tests/contract/mcp/test_tool_invocation_contract.py tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py tests/unit/api/test_metadata_service.py tests/integration/api/test_api_workflow_routes.py"`
- `P27_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/eval/test_p27_dependency_evidence_hard_live_gate.py"`
- `git diff --check`
