# P17C Draft Quality Audit Binding

## 목표

P17B의 passed validation package와 동일한 artifact/version에 대해 초안 품질 증거를 감사 가능한 형태로 바인딩한다. quality, validation, artifact, selected object, evidence refs, correlation id가 서로 추적 가능해야 한다.

PPM은 pilot analysis target DB이고 PLF는 platform DB다. blocker가 생기면 coordinator에게 정확히 보고한다. row data 조회와 procedure execution은 금지한다.

## 읽어야 할 기준 파일

- `POLICY.md`, `EVAL_SPEC.md`
- `docs/live-pilot-blocker-closure-plan.md`
- `fixtures/eval/live_pilot_blocker_closure_p17_v1.yaml`
- `fixtures/eval/live_pilot_artifact_validation_p17_v1.yaml`
- `fixtures/eval/validation_approval_audit_p13_v1.yaml`
- `apps/api/api_app/tracking.py`
- `apps/api/api_app/workflow.py`
- `apps/api/api_app/lifecycle.py`
- `tests/unit/api/**`, `tests/integration/api/**`, `tests/eval/**`

## 허용 수정 경로

- `fixtures/eval/draft_quality_audit_p17_v1.yaml`
- `fixtures/eval/live_pilot_blocker_closure_p17_v1.yaml`
- `tests/unit/api/**`
- `tests/integration/api/**`
- `tests/eval/**`
- `docs/live-pilot-blocker-closure-plan.md`

## 금지 경로

- `services/mssql-mcp/**`
- `packages/analysis/**`
- `packages/generation/**`
- `packages/validation/**`
- `spec/openapi/**` 직접 변경
- `spec/policy/**`
- `db/schema/**`
- `.env.example` secret 추가
- 사람이 수행하는 승인/리뷰 플로우, publish/export 구현, 자동 DDL/DML, row-data 조회

## 구현 범위

- P17B validation package가 `PASSED`일 때만 draft-quality evidence binding을 기록한다.
- `draft_quality_audit_p17_v1.yaml`에는 `draftQualityDecision: ACCEPT_DRAFT`, `qualityRef`, `validationRef`, `artifactRef`, `artifactVersion`, `actor`, `timestamp`, `correlationId`, `selectedObjectRefs`, `evidenceRefs`를 포함한다.
- audit event에는 actor, action, artifact ref, validation ref, quality ref, selected object refs, evidence refs, timestamp, correlation id를 포함한다.
- publish/export endpoint를 새로 만들지 않는다.

## 검증 명령

- `make test PYTEST_ARGS="tests/unit/api tests/integration/api tests/eval"`
- `python3.14 -m compileall apps/api tests/unit/api tests/integration/api tests/eval`
- 필요 시 `make test PYTEST_ARGS="tests/e2e tests/eval"`

## Blocker 보고 기준

- P17B validation package가 없거나 `PASSED`가 아님
- quality evidence가 없거나 최신 artifact/version 및 validation report에 연결되지 않음
- audit evidence가 correlation id, actor, artifact, validation, quality, selected object refs를 연결하지 못함
- OpenAPI/domain/policy/DB schema 변경 없이는 quality/audit contract를 표현할 수 없음
