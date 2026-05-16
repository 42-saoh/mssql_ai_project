# P10 MSSQL Metadata MCP Productionization


## 공통 운영 철학

- 현재 대화 요청과 첨부 ZIP의 실제 파일 구조를 최우선 기준으로 삼는다.
- P00~P07의 worktree 병렬 개발, Docker 테스트 격리, read-only metadata, draft-only generation, validation/evidence/audit 원칙을 유지한다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이다. PPM 이 없거나 접근 불가하면 PLF 로 대체하지 않고 blocker 로 보고한다.
- 실제 row data 조회, procedure 실행, 자동 DDL/DML, 운영 DB 직접 변경, 승인 없는 배포 자동화는 금지한다.
- 비밀값, 실제 비밀번호, 토큰, 실데이터는 코드/문서/fixture/test snapshot 에 넣지 않는다.
- skeleton/stub/fixture-first/optional-live/production-ready 상태를 구분해서 기록한다.
- 공유 contract/policy/common 파일 수정이 필요하면 worker가 임의로 수정하지 말고 coordinator에게 blocker로 보고한다.
- 첫 응답에는 수정 예정 파일, 검증 명령, blocker 후보를 짧게 제시한다.


## 목표

MSSQL Metadata MCP를 production target에 맞게 확장 설계·구현한다. procedure/table/search 중심 MVP에서 dependencies, indexes, constraints, extended properties, view/function metadata evidence까지 확장하고 optional live DB와 fixture fallback을 분리한다.

## 읽어야 할 기준 파일

- `PROJECT.md`, `ARCHITECTURE.md`, `POLICY.md`, `TOOLS.md`
- `docs/productization-architecture-gap-analysis.md`
- `ops/codex-parallel/PRODUCTIZATION_RELEASE_BACKLOG.md`
- `fixtures/eval/productization_readiness_v1.yaml`
- `.env.example`
- `config/mssql/local_docker_profiles.yaml`
- `services/mssql-mcp/README.md`
- `services/mssql-mcp/mssql_mcp_app/**`
- `spec/mcp/mssql_metadata_tool_catalog.yaml`
- `fixtures/mcp/**`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- `tests/contract/mcp/**`
- `tests/unit/mcp/**`
- `tests/unit/test_mcp_catalog.py`
- `tests/unit/test_mssql_mcp_live_config.py`
- `tests/contract/test_local_mssql_connection_assets.py`

## 허용 수정 경로

- `services/mssql-mcp/**`
- `spec/mcp/**`
- `tests/contract/mcp/**`
- `tests/unit/mcp/**`
- `tests/unit/test_mcp_catalog.py`
- `tests/unit/test_mssql_mcp_live_config.py`
- `tests/contract/test_local_mssql_connection_assets.py`
- `fixtures/mcp/**`

## 금지 경로

- `apps/**`
- `packages/domain/**`
- `packages/analysis/**`
- `packages/generation/**`
- `packages/validation/**`
- `spec/openapi/**`
- `spec/policy/**`
- `db/schema/**`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`

## 구현 범위

- 기존 `get_procedure_definition`, `get_procedure_parameters`, `get_table_schema`, `search_tables`의 product response shape를 표준화한다.
- dependencies, indexes, constraints, extended properties, views, functions metadata evidence tool을 catalog와 registry에 맞춰 추가한다.
- read-only query guard는 free-form SQL을 허용하지 않고 정형 metadata query만 허용한다.
- `dbProfileId=ppm`은 PPM pilot selection/eval에 사용하고, `dbProfileId=plf`는 platform DB metadata 경계로만 사용한다.
- optional live DB와 fixture fallback을 명시적으로 분리하고, timeout/retry/error code를 표준화한다.
- metadata evidence에는 snapshot id, collectedAt, source profile, object identity, permission/definition/dependency caveat를 포함한다.
- PPM manifest가 template-only이면 live integration test는 skip/xfail이 아니라 env-gated optional 경로로 둔다.

## 검증 명령

- `make test PYTEST_ARGS="tests/contract/mcp tests/unit/mcp tests/unit/test_mcp_catalog.py tests/unit/test_mssql_mcp_live_config.py tests/contract/test_local_mssql_connection_assets.py"`
- `python3.14 -m compileall services/mssql-mcp tests/contract/mcp tests/unit/mcp`
- live enabled 환경이 있으면 secret 없이 `MSSQL_ENABLE_LIVE_METADATA=1` smoke 결과를 보고

## Blocker 보고 기준

- MCP catalog 변경이 OpenAPI/domain 변경을 요구함
- PPM DB 없음, 접근 권한 없음, metadata 권한 부족
- SP definition 또는 dependency metadata 권한 부족
- read-only guard를 깨지 않고 필요한 metadata를 얻을 수 없음
- live adapter 구현에 실제 credentials, row data, DB lifecycle automation이 필요함
