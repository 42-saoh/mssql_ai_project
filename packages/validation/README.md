# packages/validation

룰 검증, evidence coverage, approval gate 관련 로직을 둘 자리다.

현재 구현 기준:

- `ai_agent_validation.load_validation_rules` 는 `spec/validation/validation_rules.yaml` 을 읽는다.
- `validate_artifact` 는 required section, evidence coverage, review-required marker 를 검증한다.
- OpenAPI requested output group 과 persisted artifact type 명칭 불일치는 `ARTIFACT_TYPE_ALIASES` 에서만 다룬다.
- `validate_publish_gate` 는 PASSED validation 과 APPROVE 결정 없이는 publish 를 실패로 판정한다.
- `validate_publish_gate(..., operation="export")` 는 같은 approval rule 로 export-like gate 도 검증한다.
- `summarize_validation_report` 와 `build_reviewer_checklist` 는 승인 로그에 저장할 deterministic summary/checklist 를 만든다.
