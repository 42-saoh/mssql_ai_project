# P17B Live Pilot Artifact Validation Closure

## 공통 운영 철학

- 현재 대화 요청과 첨부 ZIP의 실제 파일 구조를 최우선 기준으로 삼는다.
- P00~P16의 worktree 병렬 개발, Docker 테스트 격리, read-only metadata, draft-only generation, validation/approval/audit 원칙을 유지한다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이다. PPM 이 없거나 접근 불가하면 PLF 로 대체하지 않고 blocker 로 보고한다.
- 실제 row data 조회, procedure 실행, 자동 DDL/DML, 운영 DB 직접 변경, 승인 없는 배포 자동화는 금지한다.
- Java/MyBatis 생성물은 draft-only이며 사람이 최종 검토/승인한다.
- 비밀값, 실제 비밀번호, 토큰, 실데이터, raw SQL definition text 는 코드/문서/fixture/test snapshot 에 넣지 않는다.
- skeleton/stub/fixture-first/optional-live/production-ready 상태를 구분해서 기록한다.
- 공유 contract/policy/common 파일 수정이 필요하면 worker가 임의로 수정하지 말고 coordinator에게 blocker로 보고한다.
- 첫 응답에는 수정 예정 파일, 검증 명령, blocker 후보를 짧게 제시한다.

## 목표

P17A에서 dependency evidence가 확인된 PPM pilot object set을 기준으로 draft-only live pilot artifacts를 만들고, release-critical validation 결과가 `PASSED`임을 재현 가능한 fixture/test로 남긴다.

## 읽어야 할 기준 파일

- `POLICY.md`, `EVAL_SPEC.md`
- `docs/live-pilot-blocker-closure-plan.md`
- `docs/pilot-release-readiness.md`
- `fixtures/eval/live_pilot_blocker_closure_p17_v1.yaml`
- `fixtures/eval/pilot_release_readiness_p16_v1.yaml`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- `fixtures/analysis/ppm_selected_sp_evidence_v1.yaml`
- `fixtures/generation/**`
- `fixtures/eval/validation_approval_audit_p13_v1.yaml`
- `packages/analysis/**`, `packages/generation/**`, `packages/validation/**`
- `tests/unit/analysis/**`, `tests/unit/generation/**`, `tests/unit/validation/**`, `tests/eval/**`

## 허용 수정 경로

- `packages/analysis/**`
- `packages/generation/**`
- `packages/validation/**`
- `fixtures/analysis/**`
- `fixtures/generation/**`
- `fixtures/eval/live_pilot_artifact_validation_p17_v1.yaml`
- `tests/unit/analysis/**`
- `tests/unit/generation/**`
- `tests/unit/validation/**`
- `tests/eval/**`

## 금지 경로

- `services/mssql-mcp/**`
- `apps/**`
- `spec/openapi/**`
- `spec/mcp/**`
- `spec/policy/**`
- `db/schema/**`
- `.env.example`에 secret 추가
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml` 임의 수정
- publish/export/live deployment 구현

## 구현 범위

- P17A가 `DEPENDENCY_METADATA_INCOMPLETE`를 닫지 못했으면 live release artifact validation을 `BLOCKED`로 유지하고, 통과로 꾸미지 않는다.
- selected PPM SP/Table/View/Function의 metadata evidence refs를 입력으로 사용한다.
- draft artifact에는 artifact id, artifact version, artifact type, selected object refs, generation manifest ref, evidence refs를 포함한다.
- validation result에는 rule id, severity, status, releaseCritical 여부, evidence refs, artifact ref를 포함한다.
- release-critical validation item이 하나라도 `FAILED` 또는 `REVIEW_REQUIRED`이면 live release는 계속 `NO_GO`다.
- Java/MyBatis 파일 초안이나 golden sample을 추가할 수 있지만, deployment-ready 또는 production-ready로 표기하지 않는다.

## 검증 명령

- `make test PYTEST_ARGS="tests/unit/analysis tests/unit/generation tests/unit/validation tests/eval"`
- `python3.14 -m compileall packages/analysis packages/generation packages/validation tests`
- 필요 시 `make test PYTEST_ARGS="tests/contract/test_generation_goldens_and_repro_assets.py"`

## Blocker 보고 기준

- P17A dependency evidence blocker가 남아 live artifact validation 기준을 만들 수 없음
- validation rule이 release-critical `REVIEW_REQUIRED`를 남김
- draft artifact가 selected object/evidence refs에 바인딩되지 않음
- artifact validation을 통과시키려면 policy/spec/domain contract 변경이 필요함
- validation 통과 주장을 하려면 row data, procedure execution, raw definition text 저장, publish/export가 필요함
