# P17A Dependency Metadata Evidence Closure

## 공통 운영 철학

- 현재 대화 요청과 첨부 ZIP의 실제 파일 구조를 최우선 기준으로 삼는다.
- P00~P16의 worktree 병렬 개발, Docker 테스트 격리, read-only metadata, draft-only generation, validation/evidence/audit 원칙을 유지한다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이다. PPM 이 없거나 접근 불가하면 PLF 로 대체하지 않고 blocker 로 보고한다.
- 실제 row data 조회, procedure execution, 자동 DDL/DML, 운영 DB 직접 변경, 승인 없는 배포 자동화는 금지한다.
- 비밀값, 실제 비밀번호, 토큰, 실데이터는 코드/문서/fixture/test snapshot 에 넣지 않는다.
- raw procedure definition text 는 fixture, docs, logs, snapshot 에 저장하지 않는다. 필요한 경우 MCP 내부에서 metadata hash/pattern 산출에만 사용한다.
- skeleton/stub/fixture-first/optional-live/production-ready 상태를 구분해서 기록한다.
- 공유 contract/policy/common 파일 수정이 필요하면 worker가 임의로 수정하지 말고 coordinator에게 blocker로 보고한다.
- 첫 응답에는 수정 예정 파일, 검증 명령, blocker 후보를 짧게 제시한다.

## 목표

P16의 `DEPENDENCY_METADATA_INCOMPLETE` blocker를 닫기 위한 metadata-only dependency evidence를 보강한다. selected PPM stored procedure가 어떤 table/view/function/procedure에 의존하는지 catalog evidence refs로 확인하고, 확인된 경우에만 selected table을 SP dependency로 주장한다.

## 읽어야 할 기준 파일

- `POLICY.md`, `TOOLS.md`, `EVAL_SPEC.md`
- `docs/pilot-release-readiness.md`
- `docs/live-pilot-blocker-closure-plan.md`
- `ops/codex-parallel/P16_PILOT_RELEASE_HANDOFF.md`
- `fixtures/eval/pilot_release_readiness_p16_v1.yaml`
- `fixtures/eval/live_pilot_blocker_closure_p17_v1.yaml`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- `fixtures/pilot/ppm_object_selection_v1/candidate_inventory_template.yaml`
- `spec/mcp/mssql_metadata_tool_catalog.yaml`
- `services/mssql-mcp/**`
- `tests/contract/mcp/**`, `tests/unit/mcp/**`, `tests/unit/test_mcp_catalog.py`

## 허용 수정 경로

- `services/mssql-mcp/**`
- `spec/mcp/mssql_metadata_tool_catalog.yaml`
- `fixtures/mcp/**`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- `fixtures/pilot/ppm_object_selection_v1/dependency_evidence_closure_v1.yaml`
- `tests/contract/mcp/**`
- `tests/unit/mcp/**`
- `tests/unit/test_mcp_catalog.py`
- `tests/contract/test_ppm_pilot_object_selection_assets.py`

## 금지 경로

- `apps/**`
- `packages/**`
- `spec/openapi/**`
- `spec/policy/**`
- `db/schema/**`
- `.env.example`에 secret 추가
- `config/mssql/local_docker_profiles.yaml` 임의 변경
- raw SQL definition text 를 fixture/docs/test snapshot 에 저장
- row data 조회 또는 row-count 기반 evidence 작성

## 구현 범위

- 기존 `get_procedure_dependencies` 및 관련 live/fixture repository surface를 점검한다.
- metadata-only dependency resolver를 보강한다. 가능한 catalog source는 `sys.sql_expression_dependencies`, `sys.objects`, `sys.schemas`, `sys.tables`, `sys.views`, `sys.procedures`, function type object, `sys.synonyms`, `sys.sql_modules`의 hash/pattern metadata이다.
- dependency item에는 가능한 범위에서 `objectType`, `schema`, `name`, `dependencyType`, `isAmbiguous`, `reviewStatus`, `resolutionStatus`, `resolutionStrategy`, `evidenceRefs`를 포함한다.
- `referenced_id`가 없지만 `referenced_schema_name`/`referenced_entity_name`으로 동일 DB catalog object가 확인되면 metadata evidence refs를 남기고 `CONFIRMED`로 승격할 수 있다.
- cross-database/server reference, dynamic SQL only reference, synonym target 불명확, 권한 부족, 모호한 이름 충돌은 `REVIEW_REQUIRED`로 유지한다.
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`은 live metadata evidence가 있을 때만 갱신한다. table 후보가 selected SP dependency가 아니면 `related_procedures`를 만들지 않는다.
- selected procedure의 release-critical table dependency가 모두 확인되지 않으면 `DEPENDENCY_METADATA_INCOMPLETE`를 active blocker로 유지한다.

## 검증 명령

- `make test PYTEST_ARGS="tests/contract/mcp tests/unit/mcp tests/unit/test_mcp_catalog.py tests/contract/test_ppm_pilot_object_selection_assets.py"`
- `python3.14 -m compileall services/mssql-mcp tests/contract/mcp tests/unit/mcp`
- live claim 전용: `P15_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/e2e tests/eval tests/contract"`

## Blocker 보고 기준

- PPM DB 없음, 접근 권한 없음, metadata read-only 권한 부족
- SP definition 또는 dependency catalog 권한 부족
- `sys.sql_expression_dependencies`와 catalog name resolution으로도 release-critical dependencies를 확인할 수 없음
- dynamic SQL, cross-database/server reference, synonym target, ambiguous name 때문에 metadata-only 확정이 불가능함
- selected table을 SP dependency로 주장하려면 raw definition text 또는 row data가 필요함
- shared contract/policy/common 파일 수정 없이는 evidence shape를 표현할 수 없음
