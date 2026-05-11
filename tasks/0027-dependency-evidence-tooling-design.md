# P27 Dependency Evidence Tooling Design

## Status

- phase: P27
- status: design/contract ready
- production_ready: false

## Goal

Strengthen the deterministic dependency evidence layer that supports AI-heavy
stored procedure analysis, without implementing new MCP handlers in this slice.
The intended outcome is fewer avoidable PPM dependency caveats and fewer
unnecessary `REVIEW_REQUIRED` markers when catalog evidence can safely confirm a
dependency.

## Scope

- Extend the `get_procedure_dependencies` contract with optional resolution
  evidence fields:
  - `resolutionConfidence`
  - `resolutionEvidenceKind`
  - `unresolvedReason`
  - `resolutionChain`
- Declare two planned, inactive, read-only MCP tools:
  - `get_dependency_closure`
  - `resolve_dependency_reference`
- Keep LLM/P24 dependency input as a dependency evidence digest, not raw SQL.
- Preserve `production_ready: false`.

## Out Of Scope

- MCP handler implementation.
- API or Web wiring.
- Runtime workflow changes.
- Persisted artifact type changes.
- Live OpenAI or live PPM gate requirements.
- Row data, procedure execution, business DB DDL/DML, raw prompt storage, raw SP
  definition storage, or raw provider response storage.

## Contract Decisions

`get_dependency_closure` accepts `dbProfileId`, `schema`, `objectName`,
`objectType`, `maxDepth`, and `includeReviewRequired`. `maxDepth` defaults to
`2` and has a hard maximum of `3`. Its output is planned as `rootObject`,
`nodes`, `edges`, `unresolved`, and `summary`; each edge carries dependency
type, resolution status/strategy, and evidence refs.

`resolve_dependency_reference` accepts a structured source object plus optional
referenced server/database/schema and required referenced name. Its output is
planned as candidates, a selected resolution only when catalog evidence is
unique, resolution status/strategy, evidence refs, and caveats.

Confirmed dependencies can feed downstream analysis as deterministic facts only
when catalog evidence is unique and high-confidence. Ambiguous names, unresolved
synonym targets, dynamic SQL markers, cross-server references without catalog
confirmation, and caller-dependent references remain `REVIEW_REQUIRED`.

## Verification

- `make test PYTEST_ARGS="tests/unit/test_mcp_catalog.py tests/contract/mcp/test_tool_invocation_contract.py"`
- `git diff --check`
