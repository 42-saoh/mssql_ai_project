# P27 Dependency Evidence Tooling Hardening Prompt Pack

## 공통 운영 철학

- 현재 대화 요청과 실제 파일 구조를 최우선 기준으로 삼는다.
- P27 은 dependency evidence tooling 을 fixture-first hardening 상태로 강화하되, API/Web 전용 invocation/workflow 는 만들지 않는 작업이다.
- `production_ready: false` 를 유지한다.
- P27 eval contract status 는 `fixture_first_hardened_with_explicit_live_gate` 로 둔다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이며, PPM 접근 실패 시 PLF fallback 은 금지한다.
- row data, procedure execution, business DB DDL/DML, free-form SQL 입력, 자동 반영, secret 저장은 금지한다.
- raw prompt, raw SP definition, raw OpenAI response text, raw provider response text 는 저장하거나 문서 예시로 복사하지 않는다.
- dependency evidence 는 snapshot, collectedAt, evidenceRefs 를 가진 structured MCP metadata digest 로만 다룬다.

## 목표

P27 dependency evidence tooling 을 fixture-first hardening 기준으로 고정한다. 기존 `get_procedure_dependencies` resolution evidence fields 를 유지하고, `get_dependency_closure` / `resolve_dependency_reference` 를 active read-only MCP tool 로 유지하되, 전용 API invocation route, Web UI, workflow wiring 은 만들지 않는다. 명시적 `P27_HARD_LIVE_GATE=1` 일 때만 PPM hard-live dependency evidence gate 를 실행한다.

## 읽어야 할 기준 파일

- `PROJECT.md`
- `ARCHITECTURE.md`
- `POLICY.md`
- `TOOLS.md`
- `EVAL_SPEC.md`
- `TASK_TEMPLATE.md`
- `spec/mcp/mssql_metadata_tool_catalog.yaml`
- `spec/eval/p27_dependency_evidence_tooling_contract.yaml`
- `services/mssql-mcp/README.md`
- `tasks/0027-dependency-evidence-tooling-design.md`
- `services/mssql-mcp/mssql_mcp_app/schema_validation.py`
- `services/mssql-mcp/mssql_mcp_app/registry.py`
- `services/mssql-mcp/mssql_mcp_app/repositories.py`
- `ops/codex-parallel/REQUEST_MANIFEST.yaml`
- `apps/api/README.md`
- `.env.example`
- `docker/test/docker-compose.yml`
- `docker/test/README.md`
- `fixtures/mcp/metadata_snapshot.json`
- `tests/unit/mcp/test_tool_registry.py`
- `tests/unit/api/test_metadata_service.py`
- `tests/integration/api/test_api_workflow_routes.py`
- `tests/eval/test_p27_dependency_evidence_hard_live_gate.py`
- `tests/unit/test_mcp_catalog.py`
- `tests/contract/mcp/test_tool_invocation_contract.py`
- `tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py`
- `tests/eval/README.md`

## 허용 수정 경로

- `spec/eval/p27_dependency_evidence_tooling_contract.yaml`
- `spec/mcp/mssql_metadata_tool_catalog.yaml`
- `services/mssql-mcp/README.md`
- `tasks/0027-dependency-evidence-tooling-design.md`
- `ops/codex-parallel/REQUEST_MANIFEST.yaml`
- `ops/codex-parallel/prompts/27_dependency_evidence_tooling_design.md`
- `services/mssql-mcp/mssql_mcp_app/schema_validation.py`
- `services/mssql-mcp/mssql_mcp_app/registry.py`
- `services/mssql-mcp/mssql_mcp_app/repositories.py`
- `apps/api/README.md`
- `.env.example`
- `docker/test/docker-compose.yml`
- `docker/test/README.md`
- `fixtures/mcp/metadata_snapshot.json`
- `tests/eval/test_p27_dependency_evidence_hard_live_gate.py`
- `tests/unit/mcp/test_tool_registry.py`
- `tests/unit/api/test_metadata_service.py`
- `tests/integration/api/test_api_workflow_routes.py`
- `tests/unit/test_mcp_catalog.py`
- `tests/contract/mcp/test_tool_invocation_contract.py`
- `tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py`
- `tests/eval/README.md`
- `EVAL_SPEC.md`
- `TOOLS.md`
- `docs/integration-eval-status.md`

## 금지 경로

- API 전용 invocation endpoint 추가
- Web UI wiring 추가
- runtime workflow 변경
- persisted artifact type 변경
- live metadata gate 또는 live OpenAI gate 를 기본 필수 검증으로 추가
- `db/schema/**`
- row data 조회 또는 row-data style fixture 저장
- procedure execution, business DB DDL/DML, 자동 apply/deploy
- free-form SQL tool input 추가
- raw prompt/raw SP definition/raw OpenAI response text/raw provider response text 저장 경로 추가
- PPM 실패 시 PLF fallback 허용

## 구현 범위

- `get_procedure_dependencies` 계약이 `resolutionConfidence`, `resolutionEvidenceKind`, `unresolvedReason`, `resolutionChain` 을 optional structured evidence 로 선언하는지 유지/검증한다.
- `get_dependency_closure` 와 `resolve_dependency_reference` 는 `active: true`, `readOnly: true`, structured-input-only, `fixture_first_hardened_with_explicit_live_gate` 상태로 catalog 에 둔다.
- fixture/live repository handler 를 harden 하고, fixture-first 범위와 mocked live unit test 에서 confirmed/synonym/caller-dependent/dynamic/cross-server/ambiguous/unresolved evidence 를 검증한다.
- `resolve_dependency_reference` 는 전체 candidate set 이 정확히 하나이고 해당 candidate 가 `CONFIRMED` + `HIGH` 일 때만 `selectedResolution` 을 채운다.
- `get_dependency_closure` 는 `includeReviewRequired=false` 인 경우에도 review-required dependency 를 `unresolved` 에 보존한다.
- `P27_HARD_LIVE_GATE=1` 과 `MSSQL_ENABLE_LIVE_METADATA=1` 이 모두 켜진 경우 `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml` 의 simple/medium/complex PPM procedure 로 hard-live closure/resolver gate 를 실행한다. gate 가 켜진 뒤 PPM 접근 실패, template-only manifest, profile/env 누락은 skip 이 아니라 blocker failure 다.
- Chakra/legacy proxy 경로에서 `python-tds` 기본 TDS negotiation 이 거부되면 로컬 host-run 검증에 한해 `MSSQL_METADATA_TDS_VERSION=7.0` 을 명시한다. 기본값은 `7.4` 이다.
- schema validator 는 `boolean` 타입과 integer `maximum` 을 검증해 `includeReviewRequired` 와 `maxDepth <= 3` 을 실제로 강제한다.
- Standard MCP response envelope 이 `snapshotId`, `collectedAt`, `evidenceRefs` 를 계속 요구하는지 확인한다.
- Confirmed dependency 만 deterministic fact 로 승격 가능하고 ambiguous/dynamic/cross-server/unconfirmed synonym/caller-dependent reference 는 `REVIEW_REQUIRED` 로 유지한다.
- 기존 `/api/v1/metadata/tools` summary 에만 새 active tool 을 노출하고, input schema/secrets/API 전용 invocation route 는 노출하지 않는다.
- P27 manifest track 과 prompt path 를 추가하고 `merge_order` 에 P27 을 P24D 이후로 고정한다.
- Contract/unit test 로 prompt/manifest/P27 fixture-first 경계를 고정한다.

## 검증 명령

- `make test PYTEST_ARGS="tests/unit/test_mcp_catalog.py tests/unit/mcp/test_tool_registry.py tests/contract/mcp/test_tool_invocation_contract.py tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py tests/unit/api/test_metadata_service.py tests/integration/api/test_api_workflow_routes.py"`
- `P27_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/eval/test_p27_dependency_evidence_hard_live_gate.py"` (명시적 hard-live 환경에서만)
- `git diff --check`

## Blocker 보고 기준

- P27 계약이나 prompt 가 `production_ready: true` 를 주장함
- P27 dependency tool 이 inactive, writable, 또는 handler 없는 상태가 됨
- free-form SQL, row data, procedure execution, business DB DDL/DML, raw definition storage, raw prompt/provider response storage, PLF fallback 을 허용함
- ambiguous/synonym/dynamic/cross-server/caller-dependent dependency 를 catalog confirmation 없이 deterministic fact 로 승격함
- `P27_HARD_LIVE_GATE=1` 상태에서 missing PPM/profile/env 를 skip 하거나 PLF fallback 으로 대체함
- P27 작업에 API 전용 invocation endpoint/Web UI/runtime workflow/persisted artifact type 구현이 섞임
