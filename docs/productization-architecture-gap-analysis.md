# P08 Productization Architecture Gap Analysis

## Summary

P00-P07 produced a starter/MVP baseline for a metadata-only MSSQL analysis, documentation, and Java/MyBatis draft-generation platform. P08 converts that baseline into productization targets for P09-P16 without changing shared contracts or implementation code.

No current surface is classified as `production-ready`. The current state is useful for bounded fixture-first validation, optional live readiness probing, and worker scoping, but product release readiness depends on the follow-up milestones in `ops/codex-parallel/PRODUCTIZATION_RELEASE_BACKLOG.md`.

## Status Taxonomy

| Status | Meaning | Release interpretation |
|---|---|---|
| `skeleton` | Route, package, UI, or document structure exists, but behavior is incomplete. | Can guide implementation; not demo evidence by itself. |
| `stub` | Placeholder or mock behavior exists with explicit review markers. | Can support local workflow shape; not product evidence. |
| `fixture-first` | Deterministic tests pass against synthetic or captured fixture metadata. | Acceptable for CI baseline and regression checks. |
| `optional-live` | Live integration can run only when external DB/profile/secret conditions are provided. | Evidence is conditional and must never fall back from PPM to PLF. |
| `production-ready` | Product behavior is contract-backed, validated, approved, documented, monitored, and safe under policy. | Target state only; not claimed by the current baseline. |

## Current State Matrix

| Surface | Current status | Evidence | Productization gap |
|---|---|---|---|
| API/BFF route surface | `fixture-first` | Request, job, artifact, validation, approval decision, metadata, and registry routes exist and are covered by API/e2e tests. | P09 must harden idempotency, errors, pagination, correlation ids, audit shape, and persistence boundaries. |
| Workflow lifecycle | `fixture-first` | Workflow reaches `REVIEW_PENDING` at `VALIDATE`; approval decisions are recorded without publishing. | P09/P13 must formalize state transitions, publish prevention, audit events, and reviewer evidence. |
| Platform DB repository | `stub` | MSSQL persistence adapter exists, but DB lifecycle and schema apply are explicitly external/manual. | P09/P13 must verify storage behavior against manually prepared PLF and report schema blockers instead of editing DDL. |
| MSSQL Metadata MCP | `fixture-first` plus `optional-live` | Tool catalog, structured invocation, read-only guard, fixture repository, PPM discovery surface, and live readiness boundary exist. | P10 must productize live read-only metadata queries, timeout/error handling, evidence caveats, and fixture/live separation. |
| PPM pilot object set | `optional-live` | `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml` is `selection_mode: live_metadata` with PPM object identities. | Dependency metadata is incomplete; SP-to-table linkage must stay `REVIEW_REQUIRED` until P10/P11 improve evidence. |
| Analysis engine | `stub` to `fixture-first` | Parser/detector helpers and canonical candidate fixture exist with `REVIEW_REQUIRED` blockers. | P11 must standardize evidence refs, confidence, dynamic SQL/temp/cursor handling, call graph, and canonical output boundaries. |
| CanonicalAnalysisModel | `skeleton` | Domain package defines enums and output mappings, but full canonical model is not implemented. | P11 must either work within a local candidate shape or raise a coordinator blocker for domain contract expansion. |
| Generation factory | `fixture-first` | SP analysis doc, dependency report, and Java/MyBatis SP wrapper drafts render deterministically with review markers. | P12 must expand template registry, manifest, golden samples, policy-based naming, and draft review checklists. |
| Validation engine | `fixture-first` | Validation rules load from spec and enforce evidence/review markers; publish gate helper requires passed validation plus approval. | P13 must productize rule taxonomy, reviewer checklist, audit linkage, and storage mappings without changing shared specs directly. |
| Web portal | `stub` | Next.js shell uses mock adapter and provides request/job/artifact preview surfaces. | P14 must add product demo flows, metadata search, API adapter smoke, blocker display, and PPM sample handling. |
| Eval/ops/readiness | `fixture-first` | P06 fixture eval covers one happy path and forbidden operations. | P15/P16 must define product metrics, observability/security checks, PPM scenarios, and go/no-go handoff package. |

## Contract Drift Matrix

| Boundary | Observed alignment | Drift or risk | Owner milestone |
|---|---|---|---|
| OpenAPI request outputs and domain artifact storage types | User-facing `RequestedOutputType` maps to persisted `ArtifactType`. | Workers must not introduce persisted types such as `JAVA_MYBATIS_DRAFT`; mapping stays in domain/API helpers. | P09/P12 |
| OpenAPI approval decision and DB approval storage | API accepts `APPROVE`, `REJECT`, `REQUEST_CHANGES`; DDL stores `APPROVED`, `REJECTED`. | Mapping is implemented in API helpers; schema/spec changes require coordinator approval. | P09/P13 |
| OpenAPI validation status and DB validation result | API exposes `PASSED`, `FAILED`, `REVIEW_REQUIRED`; DDL stores `PASS`, `FAIL`. | `REVIEW_REQUIRED` maps to storage failure semantics and must remain explicit in reports. | P13 |
| Registry type values | API has `PROMPT`, `TEMPLATE`, `POLICY`, `DB_PROFILE`, `GENERATOR`; DDL uses `PROMPT`, `TEMPLATE`, `MODEL_POLICY`, `DB_PROFILE_POLICY`. | API mapping is documented as an adapter concern; shared contract changes are blockers. | P09/P13 |
| MCP catalog and MCP registry | Catalog includes P08A minimum metadata discovery tools and read-only error codes. | P10 must harden response shape, live query behavior, caveats, timeout/retry, and fixture/live split. | P10 |
| Validation rules and implementation | Rule IDs cover evidence, publish gate, read-only MCP, uncertainty markers, schema policy, and dockerized tests. | New rule taxonomy or severity changes require spec updates outside worker scope. | P13 |
| Domain model and analysis/generation | Enums and mappings exist; full canonical model remains a candidate fixture. | P11/P12 must mark canonical gaps `REVIEW_REQUIRED` unless coordinator expands domain contract. | P11/P12 |
| DB schema and repository behavior | Versioned DDL exists; repository does not own DB lifecycle or schema apply. | Product workflows must use externally managed PLF and never auto-apply DDL. | P09/P13/P16 |
| Policy and implementation | Row data, procedure execution, auto DDL/DML, direct deployment, and unapproved publish remain forbidden. | Any product request that requires those actions is a blocker, not an implementation task. | All |

## PPM Pilot Readiness Interpretation

The P08A pilot manifest is the only source of PPM object identities for productization work:

- Manifest path: `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- Current mode: `live_metadata`
- Source DB: `PPM`
- Platform DB context: `PLF`
- Active blocker: `DEPENDENCY_METADATA_INCOMPLETE`

When `selection_mode` is `live_metadata`, P09-P16 may reference the selected PPM object identities for metadata-only fixtures, demos, and readiness reports. They must still preserve the active dependency blocker and avoid claims that stored procedures are linked to selected tables unless later metadata evidence confirms that relationship.

When `selection_mode` is `template_only`, workers must not invent object names. Eval, demo, and release readiness should remain blocker-dependent and use synthetic/fixture-first samples only.

In both modes, the following remain forbidden: row-data reads, procedure execution, SQL definition text copied into fixtures, automatic DDL/DML, PLF fallback for PPM, committed secrets, and unapproved publish or deployment automation.

## Milestone Gate Mapping

| Milestone | Uses PPM manifest for | Readiness gate |
|---|---|---|
| P09 | API request/job/artifact fixture examples. | PPM object ids only when manifest is `live_metadata`; otherwise report blocker. |
| P10 | Live metadata tool hardening and PPM profile smoke. | Read-only metadata evidence includes snapshot, source profile, caveats, and no row data. |
| P11 | Simple/medium/complex SP analysis fixtures. | Dependency confidence remains review-required until table links are confirmed. |
| P12 | Generation golden candidates and review checklist examples. | Draft-only output with evidence refs and TODO markers; no generated source auto-apply. |
| P13 | Validation/approval/audit scenarios. | Publish remains blocked without passed validation and human approval evidence. |
| P14 | Demo object selector and portal sample requests. | UI labels metadata caveats and never exposes row-data/DDL/publish controls. |
| P15 | Eval, observability, security, and ops metrics. | Metrics separate fixture-first, optional-live, and blocker-dependent evidence. |
| P16 | Pilot release readiness and handoff package. | Go/no-go includes PPM access, dependency evidence, validation results, approval/audit, and policy compliance. |

