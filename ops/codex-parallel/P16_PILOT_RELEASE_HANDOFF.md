# P16 Pilot Release Handoff

## Decision

Live pilot release: CONDITIONAL_GO.

Fixture-first/demo handoff: GO WITH LIMITATIONS.

This handoff is based on `docs/pilot-release-readiness.md` and
`fixtures/eval/pilot_release_readiness_p16_v1.yaml`. The PPM manifest is `live_metadata`, so
selected object identities may be referenced. P17A has closed `DEPENDENCY_METADATA_INCOMPLETE`
under the selected stored procedure suite majority gate. P17B passed live pilot artifact
validation, P17C bound draft-quality audit evidence, and P17D hard-live gates passed, so the
scoped draft-only live pilot candidate is now `CONDITIONAL_GO`.

## Evidence Package

- Primary report: `docs/pilot-release-readiness.md`
- Machine-readable gate: `fixtures/eval/pilot_release_readiness_p16_v1.yaml`
- Pilot object manifest: `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- P15 eval/ops gate: `fixtures/eval/eval_observability_security_ops_p15_v1.yaml`
- P17B validation package: `fixtures/eval/live_pilot_artifact_validation_p17_v1.yaml`
- P17C draft-quality audit package: `fixtures/eval/draft_quality_audit_p17_v1.yaml`
- P13 validation/evidence/audit fixture: `fixtures/eval/validation_approval_audit_p13_v1.yaml`
- Productization backlog: `ops/codex-parallel/PRODUCTIZATION_RELEASE_BACKLOG.md`

## Active Blockers

None for the scoped draft-only live pilot candidate. If P17B validation, P17C draft-quality audit
binding, or P17D hard-live verification cannot be reproduced, the decision returns to `NO_GO`.

## Verification Commands

Run the default reproducibility gate from the repository root:

```bash
make test
make test-web-smoke
make test PYTEST_ARGS="tests/e2e tests/eval tests/contract"
python3.14 -m compileall apps services packages tests
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
- Do not publish/export from this draft-generation product surface.
- Do not commit credentials or raw definition text.
- Do not change `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml` in P16.

## Conditional Scope

- Generated artifacts remain draft-only.
- No publish/export, deployment, DDL/DML execution, row-data access, procedure execution, or PLF fallback is authorized.
- The platform is not production-ready; this is only a scoped live pilot candidate decision.
- Future reruns must keep PPM read-only metadata access available and must not replace PPM with PLF.
