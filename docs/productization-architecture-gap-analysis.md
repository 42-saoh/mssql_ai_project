# P08 Productization Architecture Gap Analysis

## Summary

P00-P07 produced a starter/MVP baseline for a metadata-only MSSQL analysis, documentation, and Java/MyBatis draft-generation platform. P08 converts that baseline into productization targets for P09-P16 without changing shared contracts or implementation code.

No current surface is classified as `production-ready`. P17D has enough evidence for a scoped
draft-only live pilot `CONDITIONAL_GO`. P18A closes the minimal versioned
`CanonicalAnalysisModel` contract. P18B records web HTTP adapter smoke and documents
production auth/RBAC source of truth. P19 adds fixture-backed auth/RBAC enforcement,
while live IdP/JWKS and PLF role lookup verification is deferred future hardening.
The current opening posture is `CONDITIONAL_GO` for controlled use, with
`production_ready: false` still explicit.
P21 moves the Web portal from runtime mock/demo flow to HTTP-only functional pages and
sets Python 3.14 as the active host/Docker baseline, but PLF and read-only PPM
prerequisites remain required before the no-mock portal gate can pass.

## Status Taxonomy

| Status | Meaning | Release interpretation |
|---|---|---|
| `skeleton` | Route, package, UI, or document structure exists, but behavior is incomplete. | Can guide implementation; not demo evidence by itself. |
| `stub` | Placeholder or mock behavior exists with explicit evidence caveats. | Can support local workflow shape; not product evidence. |
| `fixture-first` | Deterministic tests pass against synthetic or captured fixture metadata. | Acceptable for CI baseline and regression checks. |
| `optional-live` | Live integration can run only when external DB/profile/secret conditions are provided. | Evidence is conditional and must never fall back from PPM to PLF. |
| `conditional-live` | Scoped live evidence passed, but only within explicit draft-only and validation-gated boundaries. | Can support a pilot candidate; not a production-ready platform claim. |
| `production-ready` | Product behavior is contract-backed, validated, documented, monitored, and safe under policy. | Target state only; not claimed by the current baseline. |

## Current State Matrix

| Surface | Current status | Evidence | Productization gap |
|---|---|---|---|
| API/BFF route surface | `fixture-first` | Request, job, artifact, validation, metadata, knowledge, and registry routes exist and are covered by API/e2e tests. | P09+ must harden idempotency, errors, pagination, correlation ids, audit shape, and persistence boundaries. |
| Workflow lifecycle | `fixture-first` | Default workflow reaches `VALIDATION_COMPLETE` at `VALIDATE`; publish/deploy/apply actions are not part of the API/UI flow. | Must keep publish prevention and audit evidence while avoiding production-ready claims. |
| Platform DB repository | `stub` | MSSQL persistence adapter exists, but DB lifecycle and schema apply are explicitly external/manual. | P09/P13 must verify storage behavior against manually prepared PLF and report schema blockers instead of editing DDL. |
| MSSQL Metadata MCP | `fixture-first` plus `optional-live` | Tool catalog, structured invocation, read-only guard, fixture repository, PPM discovery surface, and live readiness boundary exist. | P10 must productize live read-only metadata queries, timeout/error handling, evidence caveats, and fixture/live separation. |
| PPM pilot object set | `optional-live` | `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml` is `selection_mode: live_metadata` with PPM object identities. | Dependency metadata is incomplete; SP-to-table linkage must stay an evidence caveat until P10/P11 improve evidence. |
| Analysis engine | `fixture-first` | Parser/detector helpers map deterministically to `CanonicalAnalysisModel` when snapshot id and registry refs are bound; uncertain findings remain evidence caveats. | Broader live analysis coverage still needs stronger PPM evidence, especially dynamic SQL and ambiguous dependencies. |
| CanonicalAnalysisModel | `fixture-first` | Domain package now defines a minimal versioned canonical contract with snapshot id, registry refs, evidence refs, dependencies, patterns, result sets, business rules, and modernization points. | Productization still needs downstream web/auth release evidence; field-level uncertainty is allowed only as explicit evidence caveats. |
| Generation factory | `fixture-first` | SP analysis doc, dependency report, and Java/MyBatis SP wrapper drafts render deterministically with evidence caveats. | P12+ must expand template registry, manifest, golden samples, policy-based naming, and draft-quality sections. |
| Validation engine | `fixture-first` | Validation rules load from spec and enforce evidence/caveat markers; publish/apply routes remain absent. | Must productize rule taxonomy, quality caveats, audit linkage, and storage mappings without changing shared specs directly. |
| Web portal | `conditional-live` | P21 runtime/default path uses HTTP API only and renders blockers when API/PLF/PPM prerequisites are missing. | Full product readiness still requires PLF/PPM live gate evidence, broader UI smoke, and no production-ready overclaim. |
| Eval/ops/readiness | `fixture-first` | P06 fixture eval covers one happy path and forbidden operations. | P15/P16 must define product metrics, observability/security checks, PPM scenarios, and go/no-go handoff package. |
| P17 scoped pilot release | `conditional-live` | P17D records `CONDITIONAL_GO` for the draft-only scoped candidate. | This does not close productization; P18 must resolve canonical contract and web/auth evidence. |
| P18/P19 productization closure | `conditional-live` | `fixtures/eval/productization_gap_closure_p18_v1.yaml` records P18A canonical closure, web HTTP adapter smoke, auth/RBAC source documentation, fixture-backed enforcement, and deferred live wiring hardening. | Controlled conditional open is allowed, but `AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED` remains required before claiming production-grade enterprise Auth/RBAC. |
| P21 no-mock functional portal | `conditional-live` | `fixtures/eval/live_portal_no_mock_p21_v1.yaml` records Python 3.14, HTTP-only Web runtime, required pages, PLF/PPM prerequisites, and no fallback policy. | `P21_LIVE_PORTAL_GATE=1` must pass in an approved environment before calling the portal live-functional; `production_ready: false` remains. |

## Contract Drift Matrix

| Boundary | Observed alignment | Drift or risk | Owner milestone |
|---|---|---|---|
| OpenAPI request outputs and domain artifact storage types | User-facing `RequestedOutputType` maps to persisted `ArtifactType`. | Workers must not introduce persisted types such as `JAVA_MYBATIS_DRAFT`; mapping stays in domain/API helpers. | P09/P12 |
| OpenAPI validation status and DB validation result | API exposes `PASSED`, `FAILED`, `REVIEW_REQUIRED`; DDL stores `PASS`, `FAIL`. | `REVIEW_REQUIRED` maps to storage failure semantics and must remain explicit in reports. | P13 |
| Registry type values | API has `PROMPT`, `TEMPLATE`, `POLICY`, `DB_PROFILE`, `GENERATOR`; DDL uses `PROMPT`, `TEMPLATE`, `MODEL_POLICY`, `DB_PROFILE_POLICY`. | API mapping is documented as an adapter concern; shared contract changes are blockers. | P09/P13 |
| MCP catalog and MCP registry | Catalog includes P08A minimum metadata discovery tools and read-only error codes. | P10 must harden response shape, live query behavior, caveats, timeout/retry, and fixture/live split. | P10 |
| Validation rules and implementation | Rule IDs cover evidence, publish gate, read-only MCP, uncertainty markers, schema policy, and dockerized tests. | New rule taxonomy or severity changes require spec updates outside worker scope. | P13 |
| Domain model and analysis/generation | Minimal `CanonicalAnalysisModel` exists and analysis reports exact blockers when snapshot id, registry refs, or evidence refs are missing. | P11/P12 must keep uncertain dynamic SQL, dependencies, business rules, and modernization points `REVIEW_REQUIRED` instead of confirmed. | P11/P12/P18A |
| DB schema and repository behavior | Versioned DDL exists; repository does not own DB lifecycle or schema apply. | Product workflows must use externally managed PLF and never auto-apply DDL. | P09/P13/P16 |
| Policy and implementation | Row data, procedure execution, auto DDL/DML, direct deployment, and unapproved publish remain forbidden. | Any product request that requires those actions is a blocker, not an implementation task. | All |

## PPM Pilot Readiness Interpretation

The P08A pilot manifest is the only source of PPM object identities for productization work:

- Manifest path: `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- Current mode: `live_metadata`
- Source DB: `PPM`
- Platform DB context: `PLF`
- Closed dependency evidence gate: `DEPENDENCY_METADATA_INCOMPLETE` is closed by the P17A selected stored procedure suite majority gate.

When `selection_mode` is `live_metadata`, P09-P18 may reference the selected PPM object identities for metadata-only fixtures, demos, and readiness reports. They must preserve the P17A dependency closure caveats and avoid claims that stored procedures are linked to selected tables unless catalog evidence confirms that relationship.

When `selection_mode` is `template_only`, workers must not invent object names. Eval, demo, and release readiness should remain blocker-dependent and use synthetic/fixture-first samples only.

In both modes, the following remain forbidden: row-data reads, procedure execution, SQL definition text copied into fixtures, automatic DDL/DML, PLF fallback for PPM, committed secrets, and unapproved publish or deployment automation.

## Milestone Gate Mapping

| Milestone | Uses PPM manifest for | Readiness gate |
|---|---|---|
| P09 | API request/job/artifact fixture examples. | PPM object ids only when manifest is `live_metadata`; otherwise report blocker. |
| P10 | Live metadata tool hardening and PPM profile smoke. | Read-only metadata evidence includes snapshot, source profile, caveats, and no row data. |
| P11 | Simple/medium/complex SP analysis fixtures. | Dependency confidence remains review-required until table links are confirmed. |
| P12 | Generation golden candidates and review checklist examples. | Draft-only output with evidence refs and TODO markers; no generated source auto-apply. |
| P13 | Validation/evidence/audit scenarios. | Publish remains absent from the draft-generation product surface. |
| P14 | Demo object selector and portal sample requests. | UI labels metadata caveats and never exposes row-data/DDL/publish controls. |
| P15 | Eval, observability, security, and ops metrics. | Metrics separate fixture-first, optional-live, and blocker-dependent evidence. |
| P16 | Pilot release readiness and handoff package. | Go/no-go includes PPM access, dependency evidence, validation results, draft-quality audit, and policy compliance. |
| P17 | Live pilot blocker closure. | Scoped draft-only candidate can become `CONDITIONAL_GO`; platform production-ready remains forbidden. |
| P18/P19 | Canonical contract, web HTTP smoke, and auth/RBAC productization closure. | Conditional open is allowed with live IdP/JWKS and PLF role lookup deferred; production-grade enterprise Auth/RBAC claims require that evidence to pass first. |
| P21 | No-mock functional portal and Python 3.14 baseline. | Web must use HTTP API, PLF and PPM must be configured for live gate, and missing prerequisites are blockers rather than mock fallback. |
