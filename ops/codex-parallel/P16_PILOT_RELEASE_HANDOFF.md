# P16 Pilot Release Handoff

## Decision

Live pilot release: NO-GO.

Fixture-first/demo handoff: GO WITH LIMITATIONS.

This handoff is based on `docs/pilot-release-readiness.md` and
`fixtures/eval/pilot_release_readiness_p16_v1.yaml`. The PPM manifest is `live_metadata`, so
selected object identities may be referenced, but `DEPENDENCY_METADATA_INCOMPLETE` remains a
release blocker.

## Evidence Package

- Primary report: `docs/pilot-release-readiness.md`
- Machine-readable gate: `fixtures/eval/pilot_release_readiness_p16_v1.yaml`
- Pilot object manifest: `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- P15 eval/ops gate: `fixtures/eval/eval_observability_security_ops_p15_v1.yaml`
- P13 validation/approval/audit fixture: `fixtures/eval/validation_approval_audit_p13_v1.yaml`
- Productization backlog: `ops/codex-parallel/PRODUCTIZATION_RELEASE_BACKLOG.md`

## Active Blockers

| Code | Impact | Owner action |
|---|---|---|
| `DEPENDENCY_METADATA_INCOMPLETE` | Blocks live pilot release because selected SPs cannot claim confirmed table lineage. | Harden PPM dependency metadata collection and analysis evidence, then rerun P15/P16 gates. |
| `MANUAL_APPROVAL_EVIDENCE_MISSING` | Blocks publish/export or live release claims. | Produce artifacts with passed validation, bind human approval, and preserve audit context. |

## Verification Commands

Run the default reproducibility gate from the repository root:

```bash
make test
make test-web-smoke
make test PYTEST_ARGS="tests/e2e tests/eval tests/contract"
python -m compileall apps services packages tests
```

Run the explicit hard-live gate before making any live PPM readiness claim:

```bash
P15_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/e2e tests/eval"
P15_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/e2e tests/eval tests/contract"
```

If the explicit P15/P16 live checks fail because PPM is unavailable, metadata permissions are
missing, or `MSSQL_ENABLE_LIVE_METADATA=1` is not configured, report the exact blocker. Do not
switch the analysis profile to PLF.

## Policy Boundaries

- Do not query row data.
- Do not execute stored procedures.
- Do not auto-apply DDL/DML.
- Do not publish/export without passed validation and human approval.
- Do not commit credentials or raw definition text.
- Do not change `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml` in P16.

## Next Owner Actions

1. Resolve `DEPENDENCY_METADATA_INCOMPLETE` by improving metadata-only dependency evidence.
2. Add live pilot validation artifacts that can reach `PASSED` without suppressing review markers.
3. Bind a human `APPROVE` decision to the latest passed validation report for any release candidate.
4. Confirm audit records include correlation id, actor, target ref, validation ref, and approval ref.
5. Re-run the full P16 verification set and update the readiness decision only after blockers close.
