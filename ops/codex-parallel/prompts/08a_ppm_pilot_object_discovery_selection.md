# P08A PPM Pilot Object Discovery & Selection


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

로컬 MSSQL 인스턴스의 `PPM` DB에서 이후 productization wave 전체가 공통으로 사용할 대표 Stored Procedure, Table, View, Function 후보를 metadata-only 방식으로 선정한다.

단, P10 전체 productization을 선행하지 않는다. P08A 안에서는 PPM pilot object selection을 실행하는 데 필요한 **최소 metadata discovery surface**만 먼저 보강할 수 있다. 이 surface는 P08A 실행을 unblock하기 위한 제한된 MCP metadata catalog/adapter/test 보강이며, P10의 broader production hardening 범위로 확장하지 않는다.

live metadata 연결이 불가능하거나 최소 discovery surface로도 선정 근거를 확보할 수 없으면 실제 오브젝트 이름을 만들지 않고 `template_only` manifest와 blocker 기준만 정리한다.

## 읽어야 할 기준 파일

- `PROJECT.md`
- `ARCHITECTURE.md`
- `TOOLS.md`
- `POLICY.md`
- `EVAL_SPEC.md`
- `.env.example`
- `config/mssql/local_docker_profiles.yaml`
- `services/mssql-mcp/README.md`
- `services/mssql-mcp/mssql_mcp_app/**`
- `spec/mcp/mssql_metadata_tool_catalog.yaml`
- `fixtures/mcp/**`
- `fixtures/pilot/ppm_object_selection_v1/README.md`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- `fixtures/pilot/ppm_object_selection_v1/candidate_inventory_template.yaml`

## 허용 수정 경로

- `fixtures/pilot/ppm_object_selection_v1/**`
- `tests/contract/test_ppm_pilot_object_selection_assets.py`
- `spec/mcp/mssql_metadata_tool_catalog.yaml`
- `services/mssql-mcp/mssql_mcp_app/catalog.py`
- `services/mssql-mcp/mssql_mcp_app/errors.py`
- `services/mssql-mcp/mssql_mcp_app/guardrails.py`
- `services/mssql-mcp/mssql_mcp_app/metadata_discovery.py`
- `services/mssql-mcp/mssql_mcp_app/registry.py`
- `services/mssql-mcp/mssql_mcp_app/repositories.py`
- `tests/contract/mcp/**`
- `tests/unit/mcp/**`
- `tests/unit/test_mcp_catalog.py`
- `fixtures/mcp/**`
- 필요한 경우 P08A 결과만 설명하는 좁은 docs 파일

## 금지 경로

- `apps/**`
- `packages/**`
- `services/mssql-mcp/**` 중 위 허용 수정 경로에 명시되지 않은 파일
- `spec/openapi/**`
- `spec/policy/**`
- `db/schema/**`
- 루트 정책/아키텍처 문서. 단, coordinator가 명시 승인한 작은 PPM/PLF 역할 문구 보정은 별도 패치로 처리
- `.env`, 실제 credential 파일, live DB dump, row-data fixture

## 구현 범위

### 1. P08A 선행 최소 metadata discovery surface

기존 MCP surface만으로 PPM pilot object selection을 수행할 수 있으면 새 tool을 만들지 말고 재사용한다. 기존 surface가 부족하면 P08A 실행에 필요한 최소 범위로만 MCP metadata discovery surface를 보강한다.

허용되는 최소 surface 예시는 다음과 같다.

- `check_database_exists` 또는 동등한 DB 존재/접근 가능성 확인 tool
- `list_procedures` 또는 동등한 procedure inventory tool
- `get_procedure_definition`
- `get_procedure_parameters`
- `get_procedure_dependencies`
- `list_tables` 또는 `search_tables`
- `get_table_schema`
- `get_table_indexes`
- `get_table_constraints`
- `get_extended_properties`
- `list_views` 또는 view identity/definition availability 조회
- `list_functions` 또는 function identity/definition availability 조회

최소 surface의 response는 P08A 선정 근거에 필요한 metadata evidence만 담는다.

- source profile: `ppm`
- source database: `PPM`
- object identity: schema/name/type
- snapshot 또는 collected timestamp
- definition access 가능 여부와 definition hash/length/pattern flag
- parameter count와 parameter metadata
- dependency summary
- table key/index/constraint/extended property summary
- permission caveat, dependency caveat, review_required flag

### 2. 엄격한 제외 범위

P08A에서 아래 작업은 하지 않는다. 필요하면 P10 또는 coordinator blocker로 넘긴다.

- P10 전체 production hardening
- API/BFF workflow 변경
- OpenAPI/domain/policy/schema 변경
- platform DB persistence 구현
- full observability, logging pipeline, retry framework 구현
- free-form SQL 실행 interface 추가
- procedure 실행, row data 조회, DDL/DML/EXEC 실행
- fixture에 실제 row sample, 실데이터, credential 기록

### 3. PPM pilot object selection

- `PPM` DB 존재 여부, 접근 가능 여부, metadata 권한 확인 절차를 문서화한다.
- live metadata 가능 시 다음 catalog만 사용해 candidate inventory를 작성한다.
  - `sys.databases`
  - `PPM.sys.procedures`, `PPM.sys.sql_modules`, `PPM.sys.parameters`
  - `PPM.sys.sql_expression_dependencies`
  - `PPM.sys.tables`, `PPM.sys.columns`, `PPM.sys.types`
  - `PPM.sys.indexes`, `PPM.sys.index_columns`
  - `PPM.sys.key_constraints`, `PPM.sys.foreign_keys`
  - `PPM.sys.extended_properties`
  - `PPM.INFORMATION_SCHEMA.*` 는 fallback 또는 보조 조회
- SP 후보는 simple/medium/complex bucket으로 분류한다.
- Table 후보는 PK/FK/index/constraint, extended property/column description, DTO/VO/Model 생성 적합성, selected SP와의 의존성을 근거로 선정한다.
- View/Function은 있으면 각각 1개 이상 선정하고, 없거나 권한상 확인 불가하면 `not_available` 또는 `review_required`로 기록한다.
- `selected_objects.yaml`에는 object identity와 metadata evidence만 담는다. 실제 row data, sample values, secrets는 기록하지 않는다.
- live metadata 불가 시 `selection_mode: template_only`, 후보 배열 empty, blocker 후보 명시 상태를 유지한다.

## 검증 명령

- `python -m pytest tests/contract/test_ppm_pilot_object_selection_assets.py tests/contract/mcp tests/unit/mcp tests/unit/test_mcp_catalog.py`
- `python -m compileall services/mssql-mcp tests`
- `python - <<'PY'` 로 `selected_objects.yaml` / `candidate_inventory_template.yaml` YAML parse 확인
- live metadata를 실제 시도한 경우에는 실행 명령, profile id, 실패/성공 원인을 secret 없이 기록한다.

## Blocker 보고 기준

- `PPM_DB_NOT_FOUND`: 같은 로컬 MSSQL 인스턴스에서 `PPM` DB를 찾을 수 없음
- `PPM_DB_ACCESS_DENIED`: metadata 계정이 PPM catalog에 접근 불가
- `METADATA_READ_ONLY_PERMISSION_INSUFFICIENT`: 필요한 sys catalog view 권한 부족
- `SP_DEFINITION_ACCESS_DENIED`: SP definition 조회 권한 부족
- `DEPENDENCY_METADATA_INCOMPLETE`: dependency metadata가 대표 후보 선정에 부족
- `PPM_PLF_ROLE_CONFLICT`: 프로젝트 파일/로컬 설정이 `PPM=pilot`, `PLF=platform` 기준과 충돌
- `LIVE_METADATA_UNAVAILABLE`: 현재 worker 환경에서 live MSSQL 연결 불가
- `MIN_METADATA_DISCOVERY_SURFACE_INSUFFICIENT`: P10 전체 범위로 넘어가지 않고는 P08A 선정 근거를 확보할 수 없음
- 실제 row data 조회가 필요해 보이는 후보는 제외하고 blocker 또는 review_required로 기록
