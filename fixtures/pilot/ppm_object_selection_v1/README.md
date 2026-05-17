# PPM Pilot Object Selection v1

이 디렉터리는 P07 이후 productization wave 에서 공통으로 사용할 **PPM 대표 pilot object set** 을 정의하기 위한 자산이다.  
`PPM` 은 pilot analysis target DB, `PLF` 는 platform DB 로 구분한다. PPM 이 없거나 접근 권한이 없으면 PLF 로 대체하지 않는다.

## 목적

- 로컬 MSSQL 2017 Docker 인스턴스의 `PPM` DB 에서 대표 Stored Procedure, Table, View, Function 후보를 metadata-only 방식으로 선정한다.
- 이후 SP analysis, MSSQL Metadata MCP, Java/MyBatis draft generation, validation, Web UI demo/eval worker 가 같은 pilot 기준을 사용하게 한다.
- 실제 row data 는 조회하지 않는다.
- live metadata 연결이 불가능한 환경에서는 실제 오브젝트 이름을 임의로 만들지 않고 `selected_objects.yaml` 을 `template_only` 로 유지한다.

## 파일

- `selected_objects.yaml` — 현재 선정 결과 또는 template-only 상태 manifest.
- `candidate_inventory_template.yaml` — P08A worker 가 live metadata 결과를 정리할 때 사용할 inventory template.

## Discovery 절차

1. `dbProfileId=ppm` 으로 `check_database_exists` 를 호출해 `PPM` 존재와 접근 가능성을 확인한다.
2. `list_procedures`, `list_tables`, `list_views`, `list_functions` 로 후보 inventory 를 만든다.
3. 후보 확정에 더 필요한 경우에만 `get_procedure_*`, `get_table_*`, `get_extended_properties` 를 호출한다.
4. 충분한 metadata evidence 가 모이면 object identity 와 요약 근거만 `selected_objects.yaml` 에 기록한다.
5. live metadata 연결 또는 권한이 부족하면 실제 이름을 만들지 않고 `template_only` 와 blocker 를 유지한다.

허용 evidence 는 profile/database, object identity, snapshot/collected timestamp, definition hash/length/pattern flag, parameter/dependency summary, key/index/constraint/extended-property summary, caveat, `review_required` 로 제한한다. Definition text, row sample, sample value, credential 은 기록하지 않는다.

## Metadata-only 허용 범위

허용 예시:

- `sys.databases` 로 `PPM` 존재 여부 확인
- `PPM.sys.procedures`, `PPM.sys.sql_modules`, `PPM.sys.parameters` 로 SP 이름, definition length, 패턴, 파라미터 확인
- `PPM.sys.sql_expression_dependencies` 로 의존성 확인
- `PPM.sys.tables`, `PPM.sys.columns`, `PPM.sys.types` 로 테이블/컬럼 구조 확인
- `PPM.sys.indexes`, `PPM.sys.index_columns`, `PPM.sys.key_constraints`, `PPM.sys.foreign_keys` 로 PK/FK/index/constraint 확인
- `PPM.sys.extended_properties` 로 설명 metadata 확인
- `PPM.INFORMATION_SCHEMA.*` 는 fallback 또는 보조 조회로만 사용

금지 예시:

- 실제 업무 테이블을 대상으로 한 전체 컬럼 조회
- row count aggregate, sample rows, top-row sampling 같은 row-level 확인
- stored procedure 실행
- DDL/DML 실행 또는 운영 DB 변경
- 비밀값, 실제 비밀번호, 토큰, 실데이터 fixture 기록

## 선정 기준

### Stored Procedure

최소 3개 이상을 권장하며, 가능하면 아래 complexity bucket 을 각각 채운다.

- `simple`: 단순 SELECT/INSERT/UPDATE/DELETE 또는 단일 주 테이블 중심, 파라미터/의존 객체가 적은 SP
- `medium`: JOIN, 분기 조건, 여러 테이블 의존성, 기본 트랜잭션 흐름이 있는 SP
- `complex`: 동적 SQL, 임시테이블, 트랜잭션, TRY/CATCH, cursor, nested procedure call, 다중 결과셋, 복잡한 의존성이 있는 SP

### Table

최소 3개 이상을 권장한다.

- PK/FK/index/constraint 가 있는 테이블
- extended property 또는 컬럼 설명이 있는 테이블
- Java DTO 생성 테스트에 적합한 컬럼 구성을 가진 테이블
- SP 후보와 실제 의존 관계가 있는 테이블 우선

### View / Function

- 존재하면 각각 1개 이상 선정한다.
- SP 또는 Table 후보와 연결되는 View/Function 을 우선한다.
- 없거나 권한상 확인 불가하면 blocker 가 아니라 `not_available` 또는 `review_required` 로 기록한다.

## Blocker 후보

- `PPM_DB_NOT_FOUND`
- `PPM_DB_ACCESS_DENIED`
- `METADATA_READ_ONLY_PERMISSION_INSUFFICIENT`
- `SP_DEFINITION_ACCESS_DENIED`
- `DEPENDENCY_METADATA_INCOMPLETE`
- `PPM_PLF_ROLE_CONFLICT`
- `LIVE_METADATA_UNAVAILABLE`
- `MIN_METADATA_DISCOVERY_SURFACE_INSUFFICIENT`

## 현재 상태

현재 첨부 ZIP 및 이 실행 환경만으로는 live PPM metadata 연결을 검증하지 않았다. 따라서 `selected_objects.yaml` 은 실제 오브젝트명을 비워 둔 `template_only` 상태다. P08A worker 가 로컬에서 `MSSQL_ENABLE_LIVE_METADATA=1`, `dbProfileId=ppm` 조건으로 metadata-only 조회를 성공시키면 `selection_mode: live_metadata` 로 갱신할 수 있다.
