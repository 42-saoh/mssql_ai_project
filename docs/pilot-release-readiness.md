# P16 Pilot Release Readiness

## Summary

Live pilot release: CONDITIONAL_GO.

Fixture-first/demo handoff: GO WITH LIMITATIONS.

No surface is production-ready. The current package is suitable for a scoped live pilot
candidate, coordinator/reviewer handoff, fixture-first demo review, and blocker triage. P17D
may now report a conditional live pilot release because P17A dependency evidence, P17B
passed artifact validation, P17C human approval/audit binding, and the hard-live P15/P16
verification gates have all passed. Generated artifacts remain draft-only and do not
authorize publish/export, DDL/DML execution, production deployment, row data access, procedure
execution, or PLF fallback. P17A has closed `DEPENDENCY_METADATA_INCOMPLETE` under the
selected stored procedure majority gate, with `dbo.PCS_PY_ManageInvoiceFldSchd_PRC` retained
as a complex sentinel residual-review case.

## Basis

- PPM manifest: `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- Manifest timestamp: `2026-05-06T21:52:50+09:00`
- Selection mode: `live_metadata`
- Source DB: `PPM`
- Platform DB context: `PLF`
- P16 eval fixture: `fixtures/eval/pilot_release_readiness_p16_v1.yaml`
- P17B validation fixture: `fixtures/eval/live_pilot_artifact_validation_p17_v1.yaml`
- P17C approval/audit fixture: `fixtures/eval/manual_approval_audit_p17_v1.yaml`
- Handoff package: `ops/codex-parallel/P16_PILOT_RELEASE_HANDOFF.md`

Because the manifest is `live_metadata`, this report may reference selected PPM object
identities. It may claim P17A selected stored procedure suite dependency evidence, but it must
not claim selected table linkage unless `related_procedures` contains catalog-confirmed refs.

## Readiness Checklist

| Gate | Status | Evidence |
|---|---|---|
| PPM representative object manifest | PASS | Manifest is `live_metadata` and records verified `ppm` to `PPM` metadata context. |
| Read-only metadata boundary | PASS | Manifest and P15 fixture require metadata-only tools, no PLF fallback, and no row data. P17D hard-live gates passed for `ppm`/`PPM`. |
| Procedure dependency evidence | PASS | P17A selected SP suite majority gate passed; `DEPENDENCY_METADATA_INCOMPLETE` is closed with complex sentinel residual review recorded. |
| Validation result | PASS | P17B live pilot artifact validation is `PASSED` with no release-critical `REVIEW_REQUIRED` item. |
| Manual approval | PASS | P17C human `APPROVE` is bound to the P17B artifact set/version and passed validation report. |
| Audit trace | PASS | P17C audit evidence links correlation id, actor, artifact refs, validation ref, approval ref, selected object refs, and evidence refs. |
| Hard-live verification | PASS | P17D reran both hard-live commands for `tests/e2e tests/eval` and `tests/e2e tests/eval tests/contract`. |
| Policy compliance | PASS | No row-data read, procedure execution, automatic DDL/DML, PLF fallback, unapproved publish, or deployment automation is included. |
| Status taxonomy | PASS | Docs distinguish implemented, skeleton, stub, fixture-first, optional-live, and not production-ready behavior. |

## Representative Object Evaluation

| Type | Object | Readiness interpretation |
|---|---|---|
| Stored procedure | `dbo.GetInspItemsCd` | Simple representative; dependency metadata is catalog-confirmed. |
| Stored procedure | `dbo.PAD_GET_BAT_LIST_PRC` | Medium representative; same-DB and same-server cross-DB dependencies are catalog-confirmed. |
| Stored procedure | `dbo.PCS_PY_ManageInvoiceFldSchd_PRC` | Complex sentinel; 61/63 dependencies are confirmed and two ambiguous function refs remain as residual review. |
| Table | `dbo.PCS_FAIR_TRD_SCTRT_VIOL_PAY_RMD_AMT_CONF` | Metadata-rich candidate; not confirmed as a dependency of selected procedures. |
| Table | `dbo.PEM_PRV` | Metadata-rich candidate; description review is required; not confirmed as selected SP dependency. |
| Table | `dbo.PEM_CTRT` | Metadata-rich candidate; description review is required; not confirmed as selected SP dependency. |
| View | `dbo.PCO_COM_CD_DTL_V` | View identity and definition hash evidence exist; no active review marker in manifest. |
| Function | `dbo.GetInitCap` | Function identity and definition hash evidence exist; no active review marker in manifest. |

## Quality Report

| Metric | Current result | Release interpretation |
|---|---|---|
| Selected object identity coverage | 1.0 | Object identities are manifest-backed in `live_metadata` mode. |
| Selected object metadata evidence coverage | 1.0 | Metadata evidence is present at identity/hash/summary level. |
| Confirmed procedure dependency suite coverage | 0.857 | P17A dependency blocker is closed by majority gate; selected table linkage is still not claimed without related refs. |
| Stored procedure review-required ratio | 0.0 | Complex sentinel residual review is recorded as a non-blocking caveat for P17A. |
| Validation pass rate for live release | 1.0 | P17B release-critical validation items passed. The default fixture workflow can still produce `REVIEW_REQUIRED` draft artifacts outside this scoped release package. |
| Manual approval status | Human approved and bound | P17C approval is tied to the P17B artifact set/version and validation report. |
| Draft artifact completeness | Scoped conditional candidate | Suitable for draft-only live pilot review, not automatic publish/export or production deployment. |

## Known Limitations And Improvements

- `COMPLEX_SENTINEL_RESIDUAL_REVIEW`: `dbo.PCS_PY_ManageInvoiceFldSchd_PRC` keeps two ambiguous function references for reviewer awareness.
- Full `CanonicalAnalysisModel` is still not implemented; canonical candidates remain `REVIEW_REQUIRED`.
- Web portal is mock-first/demo-oriented; P18B HTTP adapter smoke is local route evidence, not a production deployment claim.
- P18/P19 records controlled conditional opening in `fixtures/eval/productization_gap_closure_p18_v1.yaml`; live IdP/JWKS and PLF role lookup evidence remains deferred future hardening before any production-grade enterprise Auth/RBAC claim.
- Publish/export is intentionally absent. Any future publish route must require passed validation and human approval.
- Platform DB persistence depends on externally managed PLF schema and data readiness; the repo does not apply schema or manage DB lifecycle.

## Go/No-Go Criteria

Live pilot release remains or returns to NO-GO if any of the following are true:

- PPM DB, metadata access, or read-only permission checks fail.
- P17A selected stored procedure suite majority dependency evidence cannot be reproduced.
- Validation remains `REVIEW_REQUIRED` or failed for live pilot artifacts.
- A human `APPROVE` decision is not bound to the latest passed validation report.
- Audit evidence lacks correlation, actor, artifact, validation, and approval context.
- The requested path requires row data, procedure execution, automatic DDL/DML, direct DB mutation, deployment automation, PLF fallback for PPM, or unapproved publish/export.

The current scoped live pilot candidate is CONDITIONAL_GO only while all of the following remain true:

- P17A selected stored procedure suite majority dependency evidence remains reproducible.
- P17B validation package remains `PASSED` with no release-critical `REVIEW_REQUIRED`.
- P17C human `APPROVE` remains bound to the latest artifact set/version and validation report.
- P17D hard-live P15/P16 verification commands pass in the target environment.
- Generated artifacts remain draft-only and no publish/export/deployment action is implied.

Fixture-first/demo handoff remains GO WITH LIMITATIONS when:

- Dockerized fixture/eval checks pass.
- Docs and eval fixtures preserve blocker state and status taxonomy.
- Reviewers understand that selected PPM object identities are metadata evidence only, not confirmed migration readiness.

## Handoff Summary

Hand off the following package to the coordinator/reviewer:

- `docs/pilot-release-readiness.md`
- `ops/codex-parallel/P16_PILOT_RELEASE_HANDOFF.md`
- `fixtures/eval/pilot_release_readiness_p16_v1.yaml`
- `fixtures/eval/live_pilot_artifact_validation_p17_v1.yaml`
- `fixtures/eval/manual_approval_audit_p17_v1.yaml`
- `tests/eval/test_p16_pilot_release_readiness.py`

Required verification before accepting this package:

- `make test`
- `make test-web-smoke`
- `make test PYTEST_ARGS="tests/e2e tests/eval tests/contract"`
- `python3.14 -m compileall apps services packages tests`

Additional verification before any live PPM readiness claim:

- `P15_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/e2e tests/eval"`
- `P15_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/e2e tests/eval tests/contract"`
