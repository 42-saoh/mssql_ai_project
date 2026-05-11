# P27 Dependency Evidence Tooling Design Prompt Pack

## 공통 운영 철학

- 현재 대화 요청과 실제 파일 구조를 최우선 기준으로 삼는다.
- P27 은 MCP handler 구현이 아니라 dependency evidence tooling design 계약과 실행 지시 자산을 정렬하는 작업이다.
- `production_ready: false` 를 유지한다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이며, PPM 접근 실패 시 PLF fallback 은 금지한다.
- row data, procedure execution, business DB DDL/DML, free-form SQL 입력, 자동 반영, secret 저장은 금지한다.
- raw prompt, raw SP definition, raw OpenAI response text, raw provider response text 는 저장하거나 문서 예시로 복사하지 않는다.
- dependency evidence 는 snapshot, collectedAt, evidenceRefs 를 가진 structured MCP metadata digest 로만 다룬다.

## 목표

P27 dependency evidence tooling 계약을 실행 가능한 prompt pack 기준으로 고정한다. 기존 `get_procedure_dependencies` resolution evidence fields 와 planned inactive/read-only dependency closure/reference resolver tool 계약을 문서, manifest, contract test 관점에서 정렬하되, 새 MCP handler/API/Web wiring 은 만들지 않는다.

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
- `ops/codex-parallel/REQUEST_MANIFEST.yaml`
- `tests/unit/test_mcp_catalog.py`
- `tests/contract/mcp/test_tool_invocation_contract.py`
- `tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py`

## 허용 수정 경로

- `spec/eval/p27_dependency_evidence_tooling_contract.yaml`
- `spec/mcp/mssql_metadata_tool_catalog.yaml`
- `services/mssql-mcp/README.md`
- `tasks/0027-dependency-evidence-tooling-design.md`
- `ops/codex-parallel/REQUEST_MANIFEST.yaml`
- `ops/codex-parallel/prompts/27_dependency_evidence_tooling_design.md`
- `tests/unit/test_mcp_catalog.py`
- `tests/contract/mcp/test_tool_invocation_contract.py`
- `tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py`
- `EVAL_SPEC.md`
- `TOOLS.md`
- `docs/integration-eval-status.md`

## 금지 경로

- MCP handler 구현 추가
- API 또는 Web wiring 추가
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
- `get_dependency_closure` 와 `resolve_dependency_reference` 는 `active: false`, `readOnly: true`, structured-input-only, `planned_p27_design_only` 상태로만 catalog 에 둔다.
- Standard MCP response envelope 이 `snapshotId`, `collectedAt`, `evidenceRefs` 를 계속 요구하는지 확인한다.
- Confirmed dependency 만 deterministic fact 로 승격 가능하고 ambiguous/dynamic/cross-server/unconfirmed synonym/caller-dependent reference 는 `REVIEW_REQUIRED` 로 유지한다.
- P27 manifest track 과 prompt path 를 추가하고 `merge_order` 에 P27 을 P24D 이후로 고정한다.
- Contract test 로 prompt/manifest/P27 design-only 경계를 고정한다.

## 검증 명령

- `make test PYTEST_ARGS="tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py tests/unit/test_mcp_catalog.py tests/contract/mcp/test_tool_invocation_contract.py"`
- `git diff --check`

## Blocker 보고 기준

- P27 계약이나 prompt 가 `production_ready: true` 를 주장함
- planned dependency tool 이 active/invokable default 로 바뀜
- free-form SQL, row data, procedure execution, business DB DDL/DML, raw definition storage, raw prompt/provider response storage, PLF fallback 을 허용함
- ambiguous/synonym/dynamic/cross-server/caller-dependent dependency 를 catalog confirmation 없이 deterministic fact 로 승격함
- P27 작업에 MCP handler/API/Web/runtime/persisted artifact type 구현이 섞임
