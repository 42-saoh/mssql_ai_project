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
