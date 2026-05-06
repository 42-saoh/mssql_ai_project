# P17C Manual Approval Audit Binding

## 공통 운영 철학

- 현재 대화 요청과 첨부 ZIP의 실제 파일 구조를 최우선 기준으로 삼는다.
- P00~P16의 worktree 병렬 개발, Docker 테스트 격리, read-only metadata, draft-only generation, validation/approval/audit 원칙을 유지한다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이다. PPM 이 없거나 접근 불가하면 PLF 로 대체하지 않고 blocker 로 보고한다.
- 실제 row data 조회, procedure execution, 자동 DDL/DML, 운영 DB 직접 변경, 승인 없는 배포 자동화는 금지한다.
- approval 은 사람이 명시적으로 남긴 결정만 인정한다. worker는 human `APPROVE`를 합성하거나 대리 생성하지 않는다.
- 비밀값, 실제 비밀번호, 토큰, 실데이터, raw SQL definition text 는 코드/문서/fixture/test snapshot 에 넣지 않는다.
- skeleton/stub/fixture-first/optional-live/production-ready 상태를 구분해서 기록한다.
- 공유 contract/policy/common 파일 수정이 필요하면 worker가 임의로 수정하지 말고 coordinator에게 blocker로 보고한다.
- 첫 응답에는 수정 예정 파일, 검증 명령, blocker 후보를 짧게 제시한다.

## 목표

P17B의 passed validation package와 동일한 artifact/version에 대해 사람이 남긴 `APPROVE` decision을 approval/audit evidence로 바인딩한다. approval, validation, artifact, selected object, evidence refs, correlation id가 서로 추적 가능해야 한다.

## 읽어야 할 기준 파일

- `POLICY.md`, `EVAL_SPEC.md`
- `docs/live-pilot-blocker-closure-plan.md`
- `fixtures/eval/live_pilot_blocker_closure_p17_v1.yaml`
- `fixtures/eval/live_pilot_artifact_validation_p17_v1.yaml` 또는 P17B 산출물
- `fixtures/eval/validation_approval_audit_p13_v1.yaml`
- `apps/api/api_app/routes/approvals.py`
- `apps/api/api_app/tracking.py`
- `apps/api/api_app/workflow.py`
- `apps/api/api_app/lifecycle.py`
- `tests/unit/api/**`, `tests/integration/api/**`, `tests/eval/**`

## 허용 수정 경로

- `apps/api/**`
- `fixtures/eval/manual_approval_audit_p17_v1.yaml`
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
- `.env.example`에 secret 추가
- human approval 합성, 자동 승인, 승인 없는 publish/export 구현

## 구현 범위

- 기존 API/workflow approval surface가 artifact/version/validation ref/correlation id를 충분히 연결하는지 확인한다.
- 부족한 경우 target path 안에서 fixture-first 또는 in-memory 수준으로 binding evidence를 보강한다. OpenAPI/shared contract 변경이 필요하면 직접 수정하지 말고 blocker로 보고한다.
- `manual_approval_audit_p17_v1.yaml`은 실제 human reviewer decision이 제공된 경우에만 `approvalDecision: APPROVE`로 작성한다.
- reviewer 입력이 없으면 approval fixture는 template 또는 `MISSING` 상태로 두고 `MANUAL_APPROVAL_EVIDENCE_MISSING`을 유지한다.
- audit event에는 actor, action, artifact ref, validation ref, approval ref, selected object refs, evidence refs, timestamp, correlation id를 포함한다.
- publish/export endpoint를 새로 만들지 않는다. 이미 있는 경로가 있다면 approval gate 없이는 차단되어야 한다.

## 검증 명령

- `make test PYTEST_ARGS="tests/unit/api tests/integration/api tests/eval"`
- `python -m compileall apps/api tests/unit/api tests/integration/api tests/eval`
- 필요 시 `make test PYTEST_ARGS="tests/e2e tests/eval"`

## Blocker 보고 기준

- P17B validation package가 없거나 `PASSED`가 아님
- human approval input이 없어 `APPROVE` evidence를 만들 수 없음
- approval이 최신 artifact/version 및 validation report와 연결되지 않음
- audit evidence가 correlation id, actor, artifact, validation, approval, selected object refs를 연결하지 못함
- OpenAPI/domain/policy/DB schema 변경 없이는 approval/audit contract를 표현할 수 없음
