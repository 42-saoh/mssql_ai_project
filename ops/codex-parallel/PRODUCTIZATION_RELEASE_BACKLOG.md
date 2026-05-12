# P08 Productization Release Backlog

## Summary

This backlog turns the P08 architecture gap analysis into worker-executable P09-P16 milestones. It is a scope and acceptance document, not an implementation command log. Workers must stay inside their prompt-owned paths and report coordinator blockers for shared contract, policy, DDL, or pilot manifest changes.

Global release rules:

- `PLF` is the platform DB and `PPM` is the pilot analysis target DB.
- PPM must not fall back to PLF.
- Generated artifacts are draft-only until validation, human review, approval, and a future publish gate allow them.
- Row-data reads, procedure execution, automatic DDL/DML, deployment automation, committed secrets, and unapproved publish are forbidden.
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml` is read-only after P08A.

## P09 API & Workflow Productization

Dependencies: P08.

Scope:

- Harden request/job/artifact/validation/approval/audit lifecycle behavior in `apps/api`.
- Add product-level API fixture examples using the PPM pilot manifest only when `selection_mode: live_metadata`.
- Keep OpenAPI/domain/DDL changes as coordinator blockers.

Acceptance criteria:

- Request submission is deterministic, idempotency/correlation behavior is documented or implemented, and status responses are consistent.
- Draft artifacts never transition to publish through this milestone.
- API error responses avoid secrets and distinguish validation, missing resource, and dependency blockers.
- PPM fixture examples preserve `DEPENDENCY_METADATA_INCOMPLETE` where applicable.

Verification:

- `make test PYTEST_ARGS="tests/integration/api tests/unit/api"`
- `python3.14 -m compileall apps/api tests/integration/api tests/unit/api`
- Optional: `make test PYTEST_ARGS="tests/contract/test_openapi_and_env_sample_assets.py"`

Blockers:

- OpenAPI/domain/DDL status model changes are required.
- Approval/audit persistence requires schema changes.
- PPM manifest is `template_only` and live object fixtures are requested.
- Auth/RBAC production enforcement becomes required in this slice.

## P10 MSSQL Metadata MCP Productionization

Dependencies: P08A.

Scope:

- Productize read-only metadata tools for procedure, dependency, table, index, constraint, extended property, view, and function evidence.
- Separate fixture and optional-live paths with explicit timeout, retry, and error-code behavior.
- Use `dbProfileId=ppm` only for PPM pilot metadata and `dbProfileId=plf` only for platform DB metadata boundaries.

Acceptance criteria:

- Tool responses include snapshot id, collected time, source profile/database, object identity, evidence refs, and caveats.
- Free-form SQL, row-data retrieval, DDL/DML, and procedure execution remain impossible through the tool surface.
- Live metadata smoke is env-gated and never required for fixture-first tests.
- PPM dependency caveats are preserved until better metadata proves linkage.

Verification:

- `make test PYTEST_ARGS="tests/contract/mcp tests/unit/mcp tests/unit/test_mcp_catalog.py tests/unit/test_mssql_mcp_live_config.py tests/contract/test_local_mssql_connection_assets.py"`
- `python3.14 -m compileall services/mssql-mcp tests/contract/mcp tests/unit/mcp`
- Optional live smoke only with approved local env: `MSSQL_ENABLE_LIVE_METADATA=1`

Blockers:

- Needed metadata requires row data, procedure execution, or write access.
- PPM DB, access, metadata permission, definition, or dependency evidence is unavailable.
- MCP catalog changes require OpenAPI/domain changes.

## P11 SP Analysis & Evidence Engine

Dependencies: P08A and P10.

Scope:

- Strengthen SP parsing and evidence extraction for signature, parameters, dependencies, call graph, transaction, TRY/CATCH, dynamic SQL, temp tables, cursors, and result-set hints.
- Use PPM simple/medium/complex procedures when live metadata exists; otherwise keep synthetic fixtures.
- Keep full `CanonicalAnalysisModel` expansion as a coordinator blocker.

Acceptance criteria:

- Analysis output separates observed evidence, inferred conclusions, TODOs, and `REVIEW_REQUIRED` fields.
- Dynamic SQL and incomplete dependency evidence lower confidence instead of fabricating links.
- PPM procedure fixtures include source profile/database and snapshot references without definition text.

Verification:

- `make test PYTEST_ARGS="tests/unit/analysis"`
- `python3.14 -m compileall packages/analysis tests/unit/analysis`
- Optional: `make test PYTEST_ARGS="tests/eval"`

Blockers:

- Domain canonical contract expansion is required.
- SP definition metadata is unavailable.
- Dependency metadata is too incomplete for requested confidence.
- Dynamic SQL internals must be treated as confirmed facts.

## P12 Java/MyBatis Generation Factory

Dependencies: P08A and P11.

Scope:

- Productize draft generation around template registry, naming policy, generation manifest, golden samples, diff summary, and review checklist.
- Keep generated outputs as reviewable artifacts, not applied source changes.
- Use PPM object identities only when the manifest is live metadata.

Acceptance criteria:

- Mapper XML, Mapper interface, service, DTO/VO/model drafts include policy version, template version, evidence refs, assumptions, and manual review checklist.
- Naming/path/namespace behavior is loaded from policy assets or reported as a blocker.
- Golden samples remain synthetic or metadata-only and contain no secrets or row data.

Verification:

- `make test PYTEST_ARGS="tests/unit/generation tests/contract/test_generation_goldens_and_repro_assets.py"`
- `python3.14 -m compileall packages/generation tests/unit/generation`
- Optional: `make test PYTEST_ARGS="tests/unit/validation"`

Blockers:

- Policy asset changes are required for naming/path consistency.
- Canonical or validation contracts must change.
- Requested behavior auto-applies generated code.
- Real data or secrets are needed in fixtures/goldens.

## P13 Validation, Approval & Audit Productization

Dependencies: P09, P11, and P12.

Scope:

- Productize validation result shape, reviewer checklist, deferred approval decision recording, audit event shape, and publish gate checks.
- Keep schema/spec changes as blockers.

Acceptance criteria:

- Validation reports include severity, pass/fail/review-required result, missing evidence, and manual review points.
- Approval recording requires current validation context and never deploys, executes DDL, or publishes by itself.
- Audit events carry correlation/actor/ref context without secrets.
- Publish gate fails without passed validation and human approval evidence.

Verification:

- `make test PYTEST_ARGS="tests/unit/validation tests/unit/api tests/integration/api"`
- `python3.14 -m compileall packages/validation apps/api tests/unit/validation tests/unit/api tests/integration/api`
- Optional: `make test PYTEST_ARGS="tests/e2e tests/eval"`

Blockers:

- Audit/approval persistence requires DB schema changes.
- Validation rule taxonomy requires spec changes.
- Artifact type/status enum drift appears.
- Any flow can publish without validation and approval.

## P14 Web Product UI

Dependencies: P09.

Scope:

- Build product demo UI flows for request creation, metadata search, job status, artifact preview, validation result, and approval/review recording.
- Keep mock-first and API adapter boundaries clear.
- Use PPM sample selector only when live metadata manifest exists.

Acceptance criteria:

- UI clearly displays draft-only, evidence, `REVIEW_REQUIRED`, blocker, and validation status.
- No UI path executes SQL, reads row data, applies DDL, deploys code, or performs publish.
- Mock data and HTTP adapter share the same portal API interface.
- PPM object samples do not invent names when manifest is template-only.

Verification:

- `make test-web-smoke`
- If available in package scripts: `pnpm --filter @mssql-agent/web lint`
- API mock path changes require TypeScript build smoke.

Blockers:

- New dependency or lockfile change is required.
- OpenAPI/API changes are required.
- Auth/RBAC production behavior becomes mandatory.
- UI action would look like deployment or automatic publish.

## P15 Evaluation, Observability, Security & Ops

Dependencies: P13 and P14.

Scope:

- Productize eval fixtures, pilot scenarios, quality metrics, latency budget, logging/monitoring, audit review, secret redaction, read-only DB permission checks, Docker reproducibility, and ops docs.
- Keep runtime app/service/package changes outside this milestone unless explicitly reassigned.

Acceptance criteria:

- Eval scenarios distinguish fixture-first, hard-live, and blocker-dependent modes.
- P15 hard-live eval is explicit. Default eval remains fixture-first, and `P15_HARD_LIVE_GATE=1` makes missing `MSSQL_ENABLE_LIVE_METADATA=1`, `dbProfileId=ppm`, `PPM`, or read-only metadata permissions fail without PLF fallback.
- Metrics include evidence coverage, review-required ratio, validation pass rate, generation reproducibility, and artifact completeness.
- Logging and audit docs define correlation ids and secret redaction.
- Read-only DB permission checks are documented without DB lifecycle automation.
- Latency budgets separate product targets from current live/fixture gate budgets.

Verification:

- `make test PYTEST_ARGS="tests/e2e tests/eval"`
- `P15_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/e2e tests/eval"`
- `python3.14 -m compileall tests`
- `bash -n scripts/*.sh`
- Optional: `make test PYTEST_ARGS="tests/contract"`

Blockers:

- Live PPM eval is required but PPM access or metadata permissions are unavailable.
- Security/audit requirements need shared contract changes.
- Performance instrumentation requires app/service code outside scope.
- Hard-live latency exceeds current gate budget.

## P16 Pilot Release Readiness

Dependencies: P15.

Scope:

- Produce pilot readiness checklist, quality report, release notes, admin/user guide updates, handoff package, and go/no-go recommendation.
- Treat PPM manifest mode as the top-level live readiness switch.

Acceptance criteria:

- Readiness report includes PPM access, metadata evidence quality, dependency caveats, validation results, approval/audit status, and policy compliance.
- `template_only` manifest mode yields blocker-dependent live release readiness.
- `live_metadata` mode still fails or cautions release if active blockers remain unresolved.
- Docs distinguish implemented, skeleton, stub, fixture-first, optional-live, and target-only capabilities.

Verification:

- `make test`
- `make test-web-smoke`
- `make test PYTEST_ARGS="tests/e2e tests/eval tests/contract"`
- `P15_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/e2e tests/eval tests/contract"`
- `python3.14 -m compileall apps services packages tests`

Blockers:

- PPM representative set is template-only.
- PPM access, definition, dependency, or read-only metadata evidence is inadequate.
- Validation/approval/audit evidence does not meet release gate.
- Any requested release path requires automatic DDL, production DB mutation, or unapproved publish.

## P18A CanonicalAnalysisModel Contract Closure

Dependencies: P17D.

Scope:

- Promote `CanonicalAnalysisModel-compatible-local-v0.2` into an explicit domain contract, or record exact contract blockers.
- Bind release-critical canonical fields to evidence refs and preserve `REVIEW_REQUIRED` for unresolved dynamic SQL, incomplete dependency evidence, and inferred business rules.
- Keep row data, procedure execution, raw definition text, PLF fallback, and automatic publish/export out of evidence.

Acceptance criteria:

- Required canonical fields are either observed with evidence refs or listed as explicit blockers.
- `DOMAIN_CANONICAL_SCHEMA_MISSING`, snapshot id, registry version refs, and modernization point gaps are implemented or recorded.
- Contract/eval tests cover required fields, status mapping, and forbidden evidence.

Verification:

- `make test PYTEST_ARGS="tests/unit/analysis tests/eval tests/contract"`
- `python3.14 -m compileall packages/analysis packages/domain tests`

Blockers:

- Shared domain contract change cannot be approved in this slice.
- Release-critical fields lack evidence refs.
- Canonical readiness requires row data, procedure execution, raw definition text, PLF fallback, or auto publish/export.

## P18B Web HTTP Adapter And Auth/RBAC Evidence

Dependencies: P17D.

Scope:

- Prove `PORTAL_API_MODE=http` against local API routes for request, job, artifact, validation, metadata search, and registry versions. P25 keeps approval decision recording as deferred server compatibility, outside the default Web smoke path.
- Keep mock adapter available for demo/dev but separate it from release evidence.
- Define production auth/RBAC source of truth, role matrix, enforcement, and negative tests, or keep `AUTH_RBAC_PRODUCTION_SOURCE_UNRESOLVED`.

Acceptance criteria:

- HTTP adapter smoke uses the same `PortalApi` interface as the mock adapter.
- No UI/API action implies publish/export, deployment, DDL/DML, row-data access, procedure execution, or PLF fallback.
- Production auth/RBAC is either implemented with tests or blocks productization.

Verification:

- `make test PYTEST_ARGS="tests/integration/api tests/e2e tests/eval"`
- `make test-web-smoke`
- `python3.14 -m compileall apps/api tests`

Blockers:

- Production actor/role source is unresolved.
- HTTP adapter cannot pass local API route smoke.
- Passing the gate would require fake auth/RBAC, row data, procedure execution, raw definition text, PLF fallback, or auto publish/export.
