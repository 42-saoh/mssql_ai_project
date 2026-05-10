# P09 API & Workflow Productization


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

API/BFF를 실제 제품 workflow 기준으로 정리한다. request, job, artifact, validation, approval, audit lifecycle을 일관된 상태 모델과 error model로 강화하고 PPM pilot object set 기반 fixture 예시를 설계한다.

## 읽어야 할 기준 파일

- `PROJECT.md`, `ARCHITECTURE.md`, `POLICY.md`, `EVAL_SPEC.md`
- `docs/productization-architecture-gap-analysis.md`
- `ops/codex-parallel/PRODUCTIZATION_RELEASE_BACKLOG.md`
- `fixtures/eval/productization_readiness_v1.yaml`
- `apps/api/README.md`
- `apps/api/api_app/**`
- `spec/openapi/ai_agent_platform_openapi_v1.yaml`
- `packages/domain/src/ai_agent_domain/models.py`
- `db/schema/ai_agent_platform_schema_v2_dbo_prefix.sql`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- `tests/integration/api/**`
- `tests/unit/api/**`

## 허용 수정 경로

- `apps/api/**`
- `tests/integration/api/**`
- `tests/unit/api/**`
- `fixtures/eval/**`

## 금지 경로

- `packages/domain/**`
- `services/mssql-mcp/**`
- `spec/**`
- `db/schema/**`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- `apps/web/**`

## 구현 범위

- request/job/artifact/validation/approval/audit lifecycle을 구현 가능한 state transition으로 정리한다.
- idempotency key, consistent status response, pagination, error code shape, correlation id/audit id를 설계하거나 skeleton에 반영한다.
- draft artifact와 approval gate를 중심으로 publish-prevention 경계를 강화한다.
- PPM pilot object manifest가 `live_metadata`일 때만 실제 object id fixture를 사용하고, `template_only`이면 object name을 만들지 않는다.
- in-memory/stub repository와 future platform DB adapter 경계를 분리한다.
- OpenAPI 또는 domain enum 변경이 필요하면 구현하지 말고 coordinator blocker로 보고한다.

## 검증 명령

- `make test PYTEST_ARGS="tests/integration/api tests/unit/api"`
- `python3.14 -m compileall apps/api tests/integration/api tests/unit/api`
- 필요 시 `make test PYTEST_ARGS="tests/contract/test_openapi_and_env_sample_assets.py"`

## Blocker 보고 기준

- OpenAPI/domain/DDL 상태 모델이 API productization에 필요한 변경을 요구함
- approval/audit lifecycle을 구현하려면 platform DB schema 변경이 필요함
- PPM pilot manifest가 template-only라 live object fixture를 만들 수 없음
- API가 MCP 또는 generation/analysis package 계약 변경 없이는 진행 불가
- 인증/RBAC 실제 구현이 필요한 범위를 넘어서야 함
