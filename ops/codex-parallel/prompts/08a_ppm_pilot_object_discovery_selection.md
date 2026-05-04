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

로컬 MSSQL 인스턴스의 `PPM` DB에서 이후 productization wave 전체가 공통으로 사용할 대표 Stored Procedure, Table, View, Function 후보를 metadata-only 방식으로 선정한다. live metadata 연결이 불가능하면 실제 오브젝트 이름을 만들지 않고 `template_only` manifest와 blocker 기준만 정리한다.

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
- `fixtures/pilot/ppm_object_selection_v1/README.md`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- `fixtures/pilot/ppm_object_selection_v1/candidate_inventory_template.yaml`

## 허용 수정 경로

- `fixtures/pilot/ppm_object_selection_v1/**`
- `tests/contract/test_ppm_pilot_object_selection_assets.py`
- 필요한 경우 P08A 결과만 설명하는 좁은 docs 파일

## 금지 경로

- `apps/**`
- `packages/**`
- `services/mssql-mcp/**` 구현 파일
- `spec/openapi/**`
- `spec/policy/**`
- `db/schema/**`
- 루트 정책/아키텍처 문서. 단, coordinator가 명시 승인한 작은 PPM/PLF 역할 문구 보정은 별도 패치로 처리
- `.env`, 실제 credential 파일, live DB dump, row-data fixture

## 구현 범위

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

- `python -m pytest tests/contract/test_ppm_pilot_object_selection_assets.py`
- `python -m compileall tests`
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
- 실제 row data 조회가 필요해 보이는 후보는 제외하고 blocker 또는 review_required로 기록
