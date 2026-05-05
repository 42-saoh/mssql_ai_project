# Integration Eval Status

## Summary

P06 adds fixture-first coverage for the implemented request → job → artifact → validation → approval decision recording path. P15 adds a hard-live eval/ops gate for PPM metadata readiness, observability, security, and reproducibility. The suite documents what is implemented now and separates stubs, fixture-first baselines, hard-live blockers, and follow-up slices.

## Current Boundaries

| Area | Status | Notes |
|---|---|---|
| API workflow | implemented | FastAPI routes submit the request, create a job, generate draft artifacts, validate, and record approval decisions. |
| Metadata collection | fixture-first | Default path uses `fixtures/mcp/metadata_snapshot.json` through the MSSQL MCP registry boundary. |
| Metadata profile | implemented | `master` is the default metadata profile; `plf` remains available for the platform DB profile. |
| Web portal | stub/skeleton | Next.js shell uses mock data by default. HTTP API smoke is follow-up. |
| Live MSSQL | hard-live for P15 eval | P15 eval requires `MSSQL_ENABLE_LIVE_METADATA=1`, `dbProfileId=ppm`, source database `PPM`, and read-only metadata permissions. Missing live PPM access is a blocker, not a skip. |
| Publish | follow-up | Publish gate helper exists, but no publish endpoint or automatic publish flow is implemented. |
| DDL | follow-up | DDL draft type exists; automatic DDL execution is forbidden and not implemented. |
| Row data | out of scope | No row-data read/write path is implemented or documented as supported. |

## Eval Assets

- `fixtures/eval/request.json`: sample OpenAPI-style request using `master.dbo.usp_GetOrderSummary`.
- `fixtures/eval/canonical_analysis_candidate.json`: sample review-required canonical candidate payload.
- `fixtures/eval/artifact_payloads.json`: expected stable workflow/artifact summary.
- `fixtures/eval/rubric.yaml`: thresholds for fixture parsing, review-required markers, evidence, forbidden states, and secret-like values.
- `fixtures/eval/eval_observability_security_ops_p15_v1.yaml`: P15 hard-live gate for PPM metadata smoke, quality metrics, latency budgets, correlation id, audit stage, redaction, and read-only DB permission checks.

## Verification Scope

`make test PYTEST_ARGS="tests/e2e tests/eval"` verifies:

- request acceptance returns `REVIEW_PENDING`
- job current step is `VALIDATE`
- persisted artifact types are generated instead of returning `JAVA_MYBATIS_DRAFT` as a storage type
- evidence and registry refs are present where implemented
- validation reports keep draft artifacts in review-required state
- approval decisions are recorded without publishing
- eval fixtures parse and match generated workflow summaries
- P15 hard-live PPM metadata calls return live evidence refs, source profile/database context, no raw definition text, no row-data shape, and latency within the current live gate budget
- P15 fixture-first workflow smoke remains deterministic and draft artifacts stay complete without publishing

For P15, the same command must run with live PPM read-only metadata access configured. If `MSSQL_ENABLE_LIVE_METADATA` is disabled or PPM access/permissions are missing, the eval suite fails with the corresponding blocker and must not fall back to PLF.

## P15 Ops Gate

- Quality metrics: evidence coverage, review-required ratio, validation pass rate, generation reproducibility, and draft artifact completeness.
- Latency budgets: separate product targets and current live gates for PPM readiness, metadata inventory smoke, and fixture workflow smoke.
- Observability: logs and audit traces must carry correlation id plus request/job/artifact/profile/snapshot/blocker context.
- Redaction: connection strings, credentials, cookies, raw definition text, and row data must not be logged or committed to fixtures.
- DB permission check: use read-only metadata tools against `ppm`/`PPM`; no row-data reads, procedure execution, DDL/DML, or PLF fallback.

## Drift Memo

- OpenAPI: no contract change in this slice. Requested output groups remain separate from persisted artifact types.
- MCP catalog: no tool surface change. Tools remain read-only and structured-argument only.
- Validation rules: no rule change. Existing evidence/review-required rules drive e2e/eval expectations.
- Policy: no policy asset change. Forbidden automatic publish, automatic DDL, and row-data access boundaries remain unchanged.
- Env/profile: default metadata profile is now consistently `master`; platform DB profile `plf` remains available.

## Follow-Up Backlog

1. Implement real read-only live metadata adapter queries behind the MCP boundary.
2. Add full CanonicalAnalysisModel domain contract and contract tests.
3. Add publish API only after validation/approval semantics are fully enforced.
4. Add web-to-API HTTP smoke once the portal is wired to a local API instance.
5. Expand eval fixtures beyond the single happy path to dynamic SQL, temp tables, transaction/TRY-CATCH, DDL drafts, and failure paths.
6. Mature DDL draft renderer while keeping schema apply/manual review outside automation.
