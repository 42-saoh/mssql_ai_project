# P21B Live API/MCP Backend Closure

## 공통 운영 철학

- 현재 대화 요청과 실제 파일 구조를 최우선 기준으로 삼는다.
- P20 Auth/RBAC live IdP/JWKS wiring 은 deferred future hardening 으로 유지한다.
- `production_ready: false` 를 유지한다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이다. PPM 이 없거나 접근 불가하면 PLF 로 대체하지 않는다.
- API/MCP 는 read-only metadata boundary 를 지킨다. row data 조회, procedure execution, business DB DDL/DML 은 금지한다.
- Approval/validation workflow write 는 PLF core platform workflow 쓰기일 때만 허용된다.

## 목표

P21 live portal 이 필요한 최소 API/BFF surface 를 실제 repository 와 MSSQL MCP metadata boundary 로 닫는다. P21 live gate 에서는 PLF repository 와 live PPM metadata 가 필수이며, fixture fallback 또는 PLF fallback 은 blocker 로 보고한다.

## 읽어야 할 기준 파일

- `ARCHITECTURE.md`
- `POLICY.md`
- `EVAL_SPEC.md`
- `apps/api/api_app/**`
- `services/mssql-mcp/**`
- `spec/openapi/ai_agent_platform_openapi_v1.yaml`
- `tests/integration/api/**`
- `tests/unit/api/**`
- `tests/contract/**`

## 허용 수정 경로

- `apps/api/**`
- `spec/openapi/ai_agent_platform_openapi_v1.yaml`
- `tests/integration/api/**`
- `tests/unit/api/**`
- `tests/eval/**`
- `tests/contract/**`
- `fixtures/eval/live_portal_no_mock_p21_v1.yaml`
- `docs/**`
- `.env.example`

## 금지 경로

- `db/schema/**`
- `config/mssql/local_docker_profiles.yaml`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- 실제 row data 조회
- stored procedure execution
- business DB DDL/DML
- PLF fallback for PPM
- publish/export/deployment 자동화
- token/secret/raw JWT claims/PLF row dump 저장

## 구현 범위

- `GET /api/v1/jobs` 로 최근 job 목록을 제공한다.
- `GET /api/v1/artifacts/{artifactId}/validation/latest` 로 page-load 에서 write 없는 validation 표시를 제공한다.
- `POST /api/v1/artifacts/{artifactId}/validation` 은 명시적 run-validation action 으로 유지한다.
- `POST /api/v1/artifacts/{artifactId}/approval-decisions` 는 persisted approval decision 기록으로 유지한다.
- `P21_LIVE_PORTAL_GATE=1` 일 때 PLF repository 와 live PPM metadata prerequisites 가 없으면 explicit blocker/error 를 반환한다.
- workflow metadata collection 과 metadata search 는 P21 live gate 에서 live read-only MCP metadata 를 사용하고 fixture fallback 을 사용하지 않는다.

## 검증 명령

- `python3.14 -m compileall apps/api services/mssql-mcp packages tests`
- `make test PYTEST_ARGS="tests/integration/api tests/unit/api tests/contract/test_openapi_and_env_sample_assets.py"`
- `P21_LIVE_PORTAL_GATE=1 make test PYTEST_ARGS="tests/eval/test_p21_live_portal_no_mock_gate.py"`

## Blocker 보고 기준

- PLF `PLATFORM_DB_*` env 또는 schema/seed prerequisites 가 없음
- PPM live metadata env 또는 MCP read-only metadata access 가 없음
- P21 live mode 에서 fixture fallback 이 필요함
- P21 live mode 에서 PLF 를 PPM 대체로 사용해야만 진행 가능함
- GO 판정을 위해 row data, procedure execution, business DB DDL/DML, publish/export/deployment, secret 저장이 필요함
