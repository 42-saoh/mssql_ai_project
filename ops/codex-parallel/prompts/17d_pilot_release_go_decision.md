# P17D Pilot Release GO Decision

## 공통 운영 철학

- 현재 대화 요청과 첨부 ZIP의 실제 파일 구조를 최우선 기준으로 삼는다.
- P00~P16의 worktree 병렬 개발, Docker 테스트 격리, read-only metadata, draft-only generation, validation/approval/audit 원칙을 유지한다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이다. PPM 이 없거나 접근 불가하면 PLF 로 대체하지 않고 blocker 로 보고한다.
- 실제 row data 조회, procedure 실행, 자동 DDL/DML, 운영 DB 직접 변경, 승인 없는 배포 자동화는 금지한다.
- 비밀값, 실제 비밀번호, 토큰, 실데이터, raw SQL definition text 는 코드/문서/fixture/test snapshot 에 넣지 않는다.
- live release 판정은 evidence 기반으로만 바꾼다. blocker가 하나라도 남으면 `NO_GO`를 유지한다.
- `CONDITIONAL_GO`는 scoped live pilot candidate에만 적용한다. 전체 플랫폼을 production-ready로 주장하지 않는다.
- 공유 contract/policy/common 파일 수정이 필요하면 worker가 임의로 수정하지 말고 coordinator에게 blocker로 보고한다.
- 첫 응답에는 수정 예정 파일, 검증 명령, blocker 후보를 짧게 제시한다.

## 목표

P17A/P17B/P17C 산출물을 검토하고 hard-live gate를 재실행한 뒤, P16 live pilot release decision을 `NO_GO` 또는 `CONDITIONAL_GO`로 갱신한다. 증거가 부족하면 절대 GO로 바꾸지 않는다.

## 읽어야 할 기준 파일

- `docs/pilot-release-readiness.md`
- `docs/live-pilot-blocker-closure-plan.md`
- `ops/codex-parallel/P16_PILOT_RELEASE_HANDOFF.md`
- `fixtures/eval/pilot_release_readiness_p16_v1.yaml`
- `fixtures/eval/live_pilot_blocker_closure_p17_v1.yaml`
- `fixtures/eval/live_pilot_artifact_validation_p17_v1.yaml` 또는 P17B 산출물
- `fixtures/eval/manual_approval_audit_p17_v1.yaml` 또는 P17C 산출물
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- `tests/e2e/**`, `tests/eval/**`, `tests/contract/**`
- `apps/**`, `services/**`, `packages/**`, `spec/**`, `db/schema/**` 는 읽기 전용 검토

## 허용 수정 경로

- `docs/pilot-release-readiness.md`
- `docs/live-pilot-blocker-closure-plan.md`
- `docs/integration-eval-status.md`
- `ops/codex-parallel/P16_PILOT_RELEASE_HANDOFF.md`
- `fixtures/eval/pilot_release_readiness_p16_v1.yaml`
- `fixtures/eval/live_pilot_blocker_closure_p17_v1.yaml`
- `tests/eval/**`

## 금지 경로

- `apps/**`
- `services/**`
- `packages/**`
- `spec/**`
- `db/schema/**`
- `.env.example`에 secret 추가
- `config/mssql/local_docker_profiles.yaml` 임의 변경
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- approval, validation, dependency evidence를 새로 합성

## 구현 범위

- P17A 산출물에서 `DEPENDENCY_METADATA_INCOMPLETE`가 실제로 닫혔는지 확인한다.
- P17B 산출물에서 live pilot artifact validation이 `PASSED`이고 release-critical `REVIEW_REQUIRED`가 없는지 확인한다.
- P17C 산출물에서 human `APPROVE`가 최신 artifact/version 및 validation report와 바인딩됐는지 확인한다.
- P15/P16 hard-live gate를 재실행하고 결과를 release evidence로 기록한다.
- 조건이 모두 맞으면 `live_pilot_release.decision`을 `CONDITIONAL_GO`로 바꾸고, 조건부 범위와 draft-only/approval boundary를 문서화한다.
- 조건 하나라도 부족하면 `NO_GO`를 유지하고 remaining blocker list를 갱신한다.

## 검증 명령

- `make test`
- `make test-web-smoke`
- `make test PYTEST_ARGS="tests/e2e tests/eval tests/contract"`
- `python -m compileall apps services packages tests`
- live claim 전용: `P15_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/e2e tests/eval"`
- live claim 전용: `P15_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/e2e tests/eval tests/contract"`

## Blocker 보고 기준

- P17A dependency evidence가 release-critical selected procedures에 대해 불완전함
- P17B validation이 `PASSED`가 아니거나 release-critical `REVIEW_REQUIRED`가 남음
- P17C human approval/audit binding이 없거나 최신 artifact/version에 연결되지 않음
- hard-live gate가 실패하거나 현재 환경에서 재현 불가
- GO로 바꾸려면 row data, procedure execution, raw definition text 저장, PLF fallback, auto publish/export가 필요함
