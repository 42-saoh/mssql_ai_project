이 디렉터리는 eval 전용 fixture 를 둔다. 합성/비식별 데이터만 사용한다.

현재 file-based interface:

- `request.json` — fixture-first OpenAPI-style request
- `canonical_analysis_candidate.json` — review-required canonical payload sample with confidence,
  TODO, result-set hint, and evidence-boundary fields
- `artifact_payloads.json` — stable workflow/artifact expectation summary
- `rubric.yaml` — pass/fail thresholds and forbidden boundary checks
- `productization_readiness_v1.yaml` — P08A PPM manifest 를 P09~P16 eval/demo/release gate 에 연결하는 metadata-only readiness fixture
- `api_productization_ppm_workflow_v1.yaml` — P09 API workflow 의 idempotency/correlation 기대값과 PPM metadata-only request 예시
- `validation_approval_audit_p13_v1.yaml` — P13 validation report, approval checklist, audit trace, publish/export gate 기대값
- `eval_observability_security_ops_p15_v1.yaml` — P15 hard-live eval/ops gate. `ppm` → `PPM` live metadata, quality metrics, latency budgets, correlation id, audit stage, redaction, read-only permission check 기대값을 정의한다.
- `pilot_release_readiness_p16_v1.yaml` — P16/P17D pilot release readiness gate. scoped live pilot release CONDITIONAL_GO, fixture-first/demo handoff GO WITH LIMITATIONS, selected PPM object evidence summary, P17A dependency closure, P17B validation, P17C approval/audit, P17D hard-live checklist 를 정의한다.
- `live_pilot_blocker_closure_p17_v1.yaml` — P17 blocker closure 와 scoped CONDITIONAL_GO 조건을 정의한다.
- `productization_gap_closure_p18_v1.yaml` — P18 CanonicalAnalysisModel, Web HTTP adapter, production auth/RBAC source/enforcement productization gap 과 blocker 를 정의한다.

P15 fixture 는 `gate_mode: hard_live` 이지만 기본 eval 실행에서는 live PPM 을 호출하지 않는다. `P15_HARD_LIVE_GATE=1` 로 명시 실행할 때 `MSSQL_ENABLE_LIVE_METADATA=1` 과 PPM read-only metadata 권한을 요구한다. PPM 이 없거나 접근 불가하면 PLF 로 대체하지 않고 blocker 로 실패한다.

P16/P17 fixture 는 PPM manifest 가 `live_metadata` 일 때만 실제 object identity 를 참조한다. `template_only` 모드에서는 object name 을 만들지 않는 정책을 유지한다. 현재 scoped live pilot 판정은 `CONDITIONAL_GO` 이지만, P18/P19 productization 판정은 live IdP/JWKS 와 PLF role lookup evidence 가 닫히기 전까지 not production-ready / NO-GO 다.
