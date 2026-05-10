# P17 Live Pilot Blocker Closure Plan

## Summary

P16 correctly keeps the live pilot release at `NO_GO`. The hard-live metadata connection is useful evidence, but it is not enough to claim release readiness. P17 is the follow-up blocker-closure wave. It must close release-critical evidence gaps without weakening the metadata-only, draft-only, approval-gated boundary.

Current live pilot decision remains `NO_GO` until all P17 exit criteria pass.

## Current Blocker Status

There are no remaining P17C manual approval blockers. The human approval evidence from
`saoh` is bound in `fixtures/eval/manual_approval_audit_p17_v1.yaml` with
`approvalDecision: APPROVE`, timestamp `2026-05-10T13:15:00+09:00`, and correlation id
`corr-p17c-human-approval-20260510`.

Current live pilot decision still remains `NO_GO` until P17D runs the hard-live gates and
updates the final release decision.

| Closed blocker | Evidence | Owner |
|---|---|---|
| `MANUAL_APPROVAL_EVIDENCE_MISSING` | Human `APPROVE` decision is bound to the P17B artifact set/version and passed validation report. | P17C |

Closed evidence gate:

| Closed item | Evidence | Owner |
|---|---|---|
| `DEPENDENCY_METADATA_INCOMPLETE` | P17A selected stored procedure suite majority dependency metadata gate passed; `dbo.PCS_PY_ManageInvoiceFldSchd_PRC` remains as complex sentinel residual review. | P17A |

A third practical gap must also be closed before the final decision can change:

| Gap | Required evidence | Closure owner |
|---|---|---|
| Live pilot artifact validation | Draft-only live pilot artifacts for the selected PPM objects must have `PASSED` validation and no release-critical `REVIEW_REQUIRED` result. | P17B |

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

3. **P17C Manual Approval & Audit Evidence Binding**
   - Record a human `APPROVE` decision only after P17B has a passed validation package.
   - Bind approval, validation, artifact version, actor, timestamp, correlation id, and audit event refs.
   - Do not synthesize reviewer approval. If no reviewer approval is provided, keep the blocker active.
   - Current P17C status is `HUMAN_APPROVED`; it closes the manual approval blocker but does not authorize publish/export or production deployment.

4. **P17D Pilot Release GO Decision Update**
   - Re-run the hard-live gates.
   - Change the release decision only if P17A, P17B, P17C, and hard-live verification all pass.
   - Otherwise preserve `NO_GO` and report the remaining blocker codes.

## GO Transition Rule

`NO_GO` may become `CONDITIONAL_GO` only when all of the following are true:

- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml` remains `selection_mode: live_metadata` for `source_db: PPM` and `platform_db_context: PLF`.
- No PLF fallback is used for PPM analysis.
- Selected stored procedure suite majority dependency metadata evidence is reproducible.
- The live pilot artifact validation package has `PASSED` status.
- No release-critical validation item remains `REVIEW_REQUIRED`.
- A human `APPROVE` decision is bound to the same artifact/version and validation report.
- Audit evidence links correlation id, actor, artifact ref, validation ref, approval ref, selected object refs, and evidence refs.
- Hard-live P15/P16 verification commands pass in the target environment.

## Mandatory Hard-Live Verification

Run these commands before making any live PPM readiness claim:

```bash
P15_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/e2e tests/eval"
P15_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/e2e tests/eval tests/contract"
```

If PPM access, metadata permissions, or live configuration fail, keep `NO_GO`. Do not switch the analysis profile to PLF.

## Forbidden Evidence And Actions

- Row data or sample rows
- Stored procedure execution
- Raw SQL definition text in fixtures, docs, logs, or snapshots
- Automatic DDL/DML
- Credential, password, token, or secret values
- PLF fallback for PPM
- Publish/export/live release claim without passed validation and human approval

## Status Taxonomy

P17 can produce one of two final outcomes:

- `NO_GO`: at least one release-critical blocker remains active, or P17D hard-live verification / final release decision is still pending.
- `CONDITIONAL_GO`: all evidence gates pass, but generated Java/MyBatis artifacts remain draft-only and still require human ownership for any downstream deployment.

P17 must not label the whole platform as `production-ready`. It can only state that the scoped live pilot release candidate has enough evidence for conditional reviewer approval.
