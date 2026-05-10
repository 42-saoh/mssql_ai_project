# P08 Product Architecture & Release Backlog


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

P00~P07 starter/MVP 상태를 productization target으로 전환하기 위한 architecture gap analysis, release backlog, acceptance criteria를 만든다. P08A의 PPM pilot object manifest를 이후 milestone/eval/demo 기준에 연결한다.

## 읽어야 할 기준 파일

- `README.md`, `PROJECT.md`, `AGENTS.md`, `ARCHITECTURE.md`, `TOOLS.md`, `POLICY.md`, `EVAL_SPEC.md`
- `spec/openapi/ai_agent_platform_openapi_v1.yaml`
- `spec/mcp/mssql_metadata_tool_catalog.yaml`
- `spec/validation/validation_rules.yaml`
- `spec/policy/**`
- `db/schema/ai_agent_platform_schema_v2_dbo_prefix.sql`
- `packages/domain/src/ai_agent_domain/models.py`
- `ops/codex-parallel/REQUEST_MANIFEST.yaml`
- `ops/codex-parallel/PARALLEL_REQUEST_PLAN.md`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- `tests/contract/test_codex_productization_prompt_pack_assets.py`

## 허용 수정 경로

- `docs/**`
- `ops/codex-parallel/**`
- `fixtures/eval/**`
- `tests/contract/test_codex_productization_prompt_pack_assets.py`

## 금지 경로

- `apps/**`
- `services/**`
- `packages/**`
- `spec/openapi/**`, `spec/mcp/**`, `spec/validation/**`, `spec/policy/**`
- `db/schema/**`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml` 직접 수정. P08A 외 worker는 읽기 전용

## 구현 범위

- starter/MVP 상태를 `skeleton`, `stub`, `fixture-first`, `optional-live`, `production-ready` 로 분류한다.
- OpenAPI, MCP catalog, validation rules, policy, domain model, DB schema 간 drift matrix를 작성한다.
- release milestone을 P09~P16 기준으로 정리한다.
- 각 milestone에 acceptance criteria와 verification command를 연결한다.
- PPM pilot object set이 `template_only`인지 `live_metadata`인지에 따라 eval/demo/release readiness 조건을 분리한다.
- product backlog는 실제 구현 명령이 아니라 worker가 실행 가능한 scope와 blocker 기준으로 작성한다.

## 검증 명령

- `make test PYTEST_ARGS="tests/contract/test_codex_productization_prompt_pack_assets.py tests/contract/test_ppm_pilot_object_selection_assets.py"`
- `python3.14 -m compileall tests`
- `python3.14 - <<'PY'` 로 `ops/codex-parallel/REQUEST_MANIFEST.yaml` YAML parse 확인

## Blocker 보고 기준

- shared contract 변경 없이는 product backlog를 정합적으로 표현할 수 없음
- PPM pilot manifest가 없거나 parse 불가
- PPM/PLF 역할 문구가 프로젝트 파일 간 충돌
- P08~P16 prompt/manifest/runbook 간 track id, prompt path, target path, dependency가 불일치
- production-ready라고 주장할 구현 근거가 없음에도 문서가 완료 상태로 오해될 위험
