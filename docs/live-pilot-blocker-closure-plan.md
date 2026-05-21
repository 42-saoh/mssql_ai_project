# P17 Live Pilot Blocker Closure Plan

## Summary

P17D has updated the scoped live pilot release candidate to `CONDITIONAL_GO`. This is a
conditional draft-quality decision, not a production-ready platform claim. The decision is
based on P17A dependency evidence, P17B passed artifact validation, P17C draft-quality audit
binding, and P17D hard-live verification, while preserving the metadata-only, draft-only
boundary.

Current live pilot decision is `CONDITIONAL_GO` for the scoped draft-only candidate.

## Current Blocker Status

There are no remaining P17C draft-quality evidence blockers. The quality evidence from
`saoh` is bound in `fixtures/eval/draft_quality_audit_p17_v1.yaml` with
`draftQualityDecision: ACCEPT_DRAFT`, timestamp `2026-05-10T13:15:00+09:00`, and correlation id
`corr-p17c-draft-quality-20260510`.

There are no remaining P17D hard-live blockers. P17D reran both hard-live gates and recorded
passed command-level evidence in `fixtures/eval/live_pilot_blocker_closure_p17_v1.yaml` and
`fixtures/eval/pilot_release_readiness_p16_v1.yaml`.

| Closed blocker | Evidence | Owner |
|---|---|---|
| `DRAFT_QUALITY_EVIDENCE_MISSING` | Draft-quality evidence is bound to the P17B artifact set/version and passed validation report. | P17C |

Closed evidence gates:

| Closed item | Evidence | Owner |
|---|---|---|
| `DEPENDENCY_METADATA_INCOMPLETE` | P17A selected stored procedure suite majority dependency metadata gate passed; `dbo.PCS_PY_ManageInvoiceFldSchd_PRC` remains as complex sentinel residual caveat. | P17A |
| Live pilot artifact validation | Draft-only live pilot artifacts for the selected PPM objects have `PASSED` validation and no release-critical `REVIEW_REQUIRED` result. | P17B |
| P17D hard-live verification | Both required hard-live commands passed against `ppm`/`PPM` with no PLF fallback. | P17D |

## P17 Execution Order

1. **P17A Dependency Metadata Evidence Closure**
   - Improve metadata-only dependency resolution for selected PPM stored procedures.
   - Confirm procedure-to-table/view/function/procedure dependencies using catalog evidence refs.
   - Update the pilot manifest only with metadata evidence; never store raw definition text or row data.
   - Close `DEPENDENCY_METADATA_INCOMPLETE` when the selected stored procedure suite majority gate is reproducible; keep complex sentinel residual review explicit.

2. **P17B Live Pilot Artifact Validation Closure**
   - Use the P17A-confirmed pilot object set to create draft-only analysis/generation artifacts.
   - Bind validation results to artifact id, artifact version, selected object refs, and evidence refs.
   - A live release candidate needs `PASSED` validation with no release-critical `REVIEW_REQUIRED` item.

3. **P17C Draft Quality & Audit Evidence Binding**
   - Record draft-quality evidence only after P17B has a passed validation package.
   - Bind quality, validation, artifact version, actor, timestamp, correlation id, and audit event refs.
   - Do not synthesize evidence. If validation-bound quality evidence is unavailable, keep the blocker active.
   - Current P17C status is `EVIDENCE_BOUND`; it closes the draft-quality blocker but does not authorize publish/export or production deployment.

4. **P17D Pilot Release GO Decision Update**
   - Re-run the hard-live gates.
   - Change the release decision only if P17A, P17B, P17C, and hard-live verification all pass.
   - Otherwise preserve `NO_GO` and report the remaining blocker codes.
   - Current P17D status is complete: the scoped candidate is `CONDITIONAL_GO`.

## GO Transition Rule

`NO_GO` may become `CONDITIONAL_GO` only when all of the following are true:

- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml` remains `selection_mode: live_metadata` for `source_db: PPM` and `platform_db_context: PLF`.
- No PLF fallback is used for PPM analysis.
- Selected stored procedure suite majority dependency metadata evidence is reproducible.
- The live pilot artifact validation package has `PASSED` status.
- No release-critical validation item remains `REVIEW_REQUIRED`.
- Draft-quality evidence is bound to the same artifact/version and validation report.
- Audit evidence links correlation id, actor, artifact ref, validation ref, quality ref, selected object refs, and evidence refs.
- Hard-live P15/P16 verification commands pass in the target environment.

## Mandatory Hard-Live Verification

Run these commands before making any live PPM readiness claim:

```bash
P15_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/e2e tests/eval"
P15_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/e2e tests/eval tests/contract"
```

If PPM access, metadata permissions, or live configuration fail in a future rerun, return to
`NO_GO`. Do not switch the analysis profile to PLF.

## Forbidden Evidence And Actions

- Row data or sample rows
- Stored procedure execution
- Raw SQL definition text in fixtures, docs, logs, or snapshots
- Automatic DDL/DML
- Credential, password, token, or secret values
- PLF fallback for PPM
- Publish/export/live release claim without passed validation and draft-quality evidence

## Status Taxonomy

P17 can produce one of two final outcomes:

- `NO_GO`: at least one release-critical blocker remains active, or P17D hard-live verification cannot be reproduced.
- `CONDITIONAL_GO`: all evidence gates pass, but generated Java/MyBatis artifacts remain draft-only and still require human ownership for any downstream deployment.

P17 must not label the whole platform as `production-ready`. It can only state that the scoped live pilot release candidate has enough evidence for conditional draft use.
