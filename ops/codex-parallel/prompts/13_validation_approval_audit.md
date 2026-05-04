# P13 Validation, Approval & Audit Productization


## 공통 운영 철학

- 현재 대화 요청과 첨부 ZIP의 실제 파일 구조를 최우선 기준으로 삼는다.
- P00~P07의 worktree 병렬 개발, Docker 테스트 격리, read-only metadata, draft-only generation, validation/approval/audit 원칙을 유지한다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이다. PPM 이 없거나 접근 불가하면 PLF 로 대체하지 않고 blocker 로 보고한다.
- 실제 row data 조회, procedure 실행, 자동 DDL/DML, 운영 DB 직접 변경, 승인 없는 배포 자동화는 금지한다.
- 비밀값, 실제 비밀번호, 토큰, 실데이터는 코드/문서/fixture/test snapshot 에 넣지 않는다.
- skeleton/stub/fixture-first/optional-live/production-ready 상태를 구분해서 기록한다.
- 공유 contract/policy/common 파일 수정이 필요하면 worker가 임의로 수정하지 말고 coordinator에게 blocker로 보고한다.
- 첫 응답에는 수정 예정 파일, 검증 명령, blocker 후보를 짧게 제시한다.


## 목표

validation rule engine, artifact validation result, reviewer checklist, approval decision log, audit event model을 product workflow로 정리한다. 사람이 최종 승인하는 구조와 재현 가능한 실행 기록을 강화한다.

## 읽어야 할 기준 파일

- `PROJECT.md`, `ARCHITECTURE.md`, `POLICY.md`, `EVAL_SPEC.md`
- `packages/validation/README.md`
- `packages/validation/src/ai_agent_validation/**`
- `spec/validation/validation_rules.yaml`
- `packages/domain/src/ai_agent_domain/models.py`
- `apps/api/api_app/**`
- `db/schema/ai_agent_platform_schema_v2_dbo_prefix.sql`
- `fixtures/eval/**`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- `tests/unit/validation/**`
- `tests/unit/api/**`
- `tests/integration/api/**`

## 허용 수정 경로

- `packages/validation/**`
- `tests/unit/validation/**`
- `fixtures/eval/**`
- `apps/api/**`
- `tests/unit/api/**`
- `tests/integration/api/**`

## 금지 경로

- `packages/domain/**`
- `packages/analysis/**`
- `packages/generation/**`
- `services/mssql-mcp/**`
- `spec/**`
- `db/schema/**`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`

## 구현 범위

- validation rule engine 결과 shape를 severity/pass/fail/missing evidence/manual review points로 표준화한다.
- reviewer checklist와 approval decision log를 API workflow와 연결한다.
- audit event model은 request/job/artifact/validation/approval 단계별로 correlation id와 actor/ref를 남긴다.
- approval gate 없는 publish나 export를 금지하는 검증을 유지한다.
- PPM pilot artifact scenario는 selected object manifest가 live_metadata일 때만 실제 object id를 사용한다.
- DB schema 변경이 필요하면 직접 수정하지 말고 blocker로 보고한다.

## 검증 명령

- `make test PYTEST_ARGS="tests/unit/validation tests/unit/api tests/integration/api"`
- `python -m compileall packages/validation apps/api tests/unit/validation tests/unit/api tests/integration/api`
- 필요 시 `make test PYTEST_ARGS="tests/e2e tests/eval"`

## Blocker 보고 기준

- audit/approval persistence에 DB schema 변경이 필요함
- validation rule taxonomy가 spec 변경 없이는 확장 불가
- artifact type/status enum drift 발견
- PPM pilot artifacts가 template-only라 representative review scenario를 만들 수 없음
- 사람 승인 없이 publish 가능한 흐름이 남아 있음
