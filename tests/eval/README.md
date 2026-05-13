이 디렉터리는 fixture/rubric 기반 eval 검증을 둔다. 기본 검증은 도커 테스트 러너를 경유한다.

현재 suite 는 `fixtures/eval/` 의 file-based assets 를 읽어 sample request, canonical candidate, artifact summary, rubric 을 검증하고, fixture-backed workflow 결과와 비교한다.

P15 부터 `eval_observability_security_ops_p15_v1.yaml` 은 hard-live gate 계약을 정의한다. 기본 `tests/eval` 실행은 fixture-first 재현성을 유지하고 live PPM 을 호출하지 않는다. `P15_HARD_LIVE_GATE=1` 로 명시 실행한 경우에만 live PPM metadata gate 를 활성화하며, 이때 `MSSQL_ENABLE_LIVE_METADATA=1`, `dbProfileId=ppm`, source database `PPM`, read-only metadata 권한이 없으면 skip 이 아니라 failure/blocker 로 보고한다. live PPM eval 은 PLF 로 fallback 하지 않는다.

실행:

```bash
make test PYTEST_ARGS="tests/eval"
```

P15 hard-live 검증을 포함하려면 worktree 의 `.env` 또는 승인된 환경변수에 PPM read-only metadata 연결 정보를 주입한 뒤 아래처럼 명시 플래그를 켠다.

```bash
P15_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/e2e tests/eval"
```

fixture-first workflow latency/reproducibility 검증은 계속 synthetic sample 로 수행한다. fixture snapshot 이나 fixture-backed metadata search 를 검증하는 테스트는 필요한 경우 `MSSQL_ENABLE_LIVE_METADATA=0` 을 test 단위에서 고정한다.

## P20 auth/RBAC live gate

P20 auth/RBAC live gate 는 기본 실행에서 skip 되며 IdP/JWKS 또는 PLF 에 접근하지 않는다.
명시적으로 `AUTH_RBAC_LIVE_GATE=1` 을 켠 경우에만
`apps/api/scripts/auth_rbac_live_probe.py` 가 `OidcJwtVerifier` 와
`MssqlPlatformRepository.resolve_actor_roles()` 로 approved test IdP/JWKS token verification
및 PLF role lookup 을 수행한다.

필수 값:

- `AUTH_RBAC_LIVE_GATE=1`
- `AUTH_RBAC_ENFORCEMENT=1`
- `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL`
- `OIDC_REVIEWER_BEARER_TOKEN`, `OIDC_USER_BEARER_TOKEN`
- 기존 `PLATFORM_DB_*`

실행:

```bash
AUTH_RBAC_LIVE_GATE=1 AUTH_RBAC_ENFORCEMENT=1 make test PYTEST_ARGS="tests/eval/test_p20_auth_rbac_live_gate.py"
```

gate 가 켜졌는데 필수 env 가 없으면 skip 이 아니라 deferred prerequisite failure 로
처리한다. 성공 전까지 `fixtures/eval/productization_gap_closure_p18_v1.yaml` 의
`AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED` 는 future hardening item 으로 유지한다.
현재 opening posture 는 controlled `CONDITIONAL_GO` 이지만 `production_ready: false` 이며,
production-grade enterprise Auth/RBAC 주장은 금지한다.

### Assisted login

Playwright MCP 는 approved non-production/test IdP 또는 dev portal 의 Assisted login
preflight 에만 사용할 수 있다. 사용자가 credentials/MFA 를 처리하고 token 은 로컬 `.env`
또는 승인된 secret manager 에 직접 넣는다. localStorage scraping, cookie scraping,
storage-state files, token-bearing screenshots, traces, recordings, chat-pasted secrets 는
금지한다.

## P21 no-mock portal live gate

P21 gate 는 기본 실행에서 skip 되며 PLF/PPM 에 접근하지 않는다. 명시적으로
`P21_LIVE_PORTAL_GATE=1` 을 켠 경우에만 PLF workflow repository 와 read-only PPM metadata
access 를 검증한다. 이 eval 은 기본 skip 결과가 PLF/PPM 초기화를 만들지 않는지, gate enabled
상태에서 필수 env 가 없으면 skip 이 아니라 `P21_LIVE_PORTAL_REQUIRED_ENV_MISSING` blocker 로
실패하는지, live prerequisites 가 준비된 경우에만 passed probe 를 허용하는지 검증한다.

```bash
P21_LIVE_PORTAL_GATE=1 make test PYTEST_ARGS="tests/eval/test_p21_live_portal_no_mock_gate.py"
```

이 gate 는 no-mock portal 의 controlled live 확인용이며 `production_ready: true` 주장이 아니다.
PPM 이 없거나 접근 불가하면 PLF 로 대체하지 않는다.

## P23 LLM SP analysis quality eval

P23/P26 eval 은 기본 실행에서 OpenAI 를 호출하지 않는다. `tests/eval/test_p23_llm_sp_analysis_quality.py` 는 `fixtures/eval/llm_sp_analysis_quality_p23_v1.yaml` 의 simple/medium/complex synthetic scenarios 를 `FakeModelGateway` 로 반복 실행하고 semantic, guide, conversion quality report 의 `status`, `productionReady`, `scores`, `thresholds`, `evidenceRefs`, `validatorResults`, sanitized storage findings 를 검증한다. Optional live confidence 는 high-quality semantic profile 을 사용하며 `OPENAI_MODEL_ANALYSIS` 로 모델을 지정할 수 있다. `openai_fast_test` / `OPENAI_MODEL_FAST_TEST` 는 수동 fast/test 선택지로만 남는다.

통과 기준은 `semantic_recall >= 0.75`, `guide_conversion_recall >= 0.8`, `evidence_discipline >= 0.9`, `unreviewed_overclaims <= 0`, `storage_safety_findings <= 0` 이다. unsupported dependency/table/function claim 은 `REVIEW_REQUIRED` 로 남아야 하고, `LLM_INFERENCE` evidence 는 deterministic fact 를 대체하지 않는다. raw prompt, raw SP definition, raw OpenAI response text, row data, secret 은 test output/report/storage payload 에 저장하지 않는다.

```bash
make test PYTEST_ARGS="tests/contract/test_p23_llm_eval_contract_prompt_assets.py tests/eval"
```

Optional live quality gate 는 confidence signal 로만 사용한다. gate 가 skip/fail/unavailable 이어도 default P23 fixture-first 결과나 production readiness 를 통과로 바꾸지 않으며, PPM 접근 실패 시 PLF fallback 은 금지한다.

```bash
LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1 make test PYTEST_ARGS="tests/eval/test_p23_openai_quality_live_gate.py"
```

## P24 SP migration guide quality eval

P24 eval 은 기본 실행에서 live OpenAI, PPM, PLF, Web/API, DB schema 에 접근하지 않는다. `tests/eval/test_p24_sp_migration_guide_quality.py` 는 `fixtures/eval/sp_migration_guide_quality_p24_v1.yaml` 의 simple/medium/complex sanitized scenarios 를 기존 `SP_ANALYSIS_DOC` 와 `DEPENDENCY_REPORT` 로 렌더링하고 `evaluate_p24_migration_guide_quality` report 를 검증한다.

통과 기준은 `required_section_coverage >= 1.0`, `evidence_linked_claim_coverage >= 0.9`, `dml_matrix_coverage >= 0.9`, `branch_call_flow_coverage >= 0.85`, `unsupported_claim_review_required_ratio >= 1.0`, `storage_safety_findings <= 0` 이다. unsupported dependency/table/function/cross-DB claim 과 low-evidence business-rule claim 은 `REVIEW_REQUIRED` 로 남아야 하고, raw prompt, raw SP definition, raw OpenAI response text, row data, secret 은 test output/report/storage payload 에 저장하지 않는다.

```bash
make test PYTEST_ARGS="tests/eval/test_p24_sp_migration_guide_quality.py tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py"
```

P24 gate 가 통과해도 `production_ready: false` 를 유지한다. Optional live confidence evidence 가 없으면 보류로 해석할 수 있지만 기본 필수 테스트로 승격하지 않으며, P25+ Java/MyBatis source expansion 은 별도 작업으로 둔다.

## P33 performance / scale

P33 eval 은 기본 실행에서 live PPM, OpenAI, queue infra, DB migration 에 접근하지 않는다.
`tests/eval/test_p33_performance_scale.py` 는 `fixtures/eval/performance_scale_p33_v1.yaml` 의 cache
reuse, stable fact hash, batch duplicate/limit, live round reduction, backpressure, no raw leakage
시나리오를 fixture-first 로 검증한다.

```bash
make test PYTEST_ARGS="tests/unit/api/test_metadata_tool_cache.py tests/unit/api/test_batch_sp_analysis.py tests/eval/test_p33_performance_scale.py"
```

이 gate 가 통과해도 process-local 최적화 confidence 만 의미하며 `production_ready: false` 를 유지한다.
Multi-process/shared cache, durable batch tracking, external queue/backpressure infra 는 후속 hardening 이다.

## P34 knowledge assetization

P34 eval 은 기본 실행에서 live PPM, OpenAI, DB migration 자동 적용에 접근하지 않는다.
`tests/eval/test_p34_knowledge_assetization.py` 는 `fixtures/eval/knowledge_assetization_p34_v1.yaml`
의 SP/metadata knowledge asset, version reuse, graph export, adversarial raw leakage 차단
시나리오를 fixture-first 로 검증한다.

```bash
make test PYTEST_ARGS="tests/unit/api/test_knowledge_asset_service.py tests/eval/test_p34_knowledge_assetization.py"
```

이 gate 가 통과해도 knowledge assets 는 draft/reviewable organizational knowledge 이며
`production_ready: false` 를 유지한다. Platform DB v5 DDL 은 수동 적용 대상이고 API/test 가
자동 적용하지 않는다.

## P35 knowledge live confidence

P35 live confidence is disabled by default. Enable `P35_KNOWLEDGE_LIVE_GATE=1` only in an
approved environment with live OpenAI, read-only PPM metadata, PLF `PLATFORM_DB_*`, and v5 DDL
already applied manually. The gate writes normal PLF workflow/knowledge/export/audit/review
records and records one real non-terminal `REVIEWED` event, but PPM remains metadata-only and
read-only.

```bash
P35_KNOWLEDGE_LIVE_GATE=1 LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1 MSSQL_ENABLE_LIVE_METADATA=1 MSSQL_METADATA_CONNECT_TIMEOUT_SECONDS=20 PLATFORM_DB_CONNECT_TIMEOUT_SECONDS=20 make test PYTEST_ARGS="tests/eval/test_p35_knowledge_live_confidence_gate.py"
```

Passing this gate is confidence evidence only. It is not production readiness, publish approval,
deployment approval, or automatic conversion approval evidence.

## P27 dependency evidence tooling

P27 은 MCP dependency evidence 계약을 fixture-first hardening 상태로 유지한다. `get_procedure_dependencies` 는 optional resolution confidence/evidence fields 를 선언하고, `get_dependency_closure` 와 `resolve_dependency_reference` 는 active/read-only/structured-input MCP tools 로 catalog 에 존재하며 fixture/live repository handler 를 가진다. P28 기준 기존 API `/api/v1/metadata/tools` summary 는 `invokable` 상태를 노출하고, 전용 invocation endpoint 는 두 P27 dependency evidence tool 만 public allowlist 로 호출한다. P29 기준 Web `/metadata/dependencies` diagnostic UI 와 workflow `get_dependency_closure` evidence wiring 이 fixture-first 로 활성화되어 있으며, persisted artifact type 과 DB schema 변경은 여전히 포함하지 않는다.

```bash
make test PYTEST_ARGS="tests/unit/test_mcp_catalog.py tests/unit/mcp/test_tool_registry.py tests/contract/mcp/test_tool_invocation_contract.py tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py tests/unit/api/test_metadata_service.py tests/unit/api/test_route_surface.py tests/integration/api/test_api_workflow_routes.py tests/contract/test_openapi_and_env_sample_assets.py"
```

이 gate 는 raw SQL input, raw SP definition 저장, raw prompt/provider response 저장, row data, procedure execution, business DB DDL/DML, PPM-to-PLF fallback 을 허용하지 않는다. Ambiguous/dynamic/unresolved synonym/cross-server/caller-dependent dependency 는 catalog confirmation 전까지 `REVIEW_REQUIRED` 로 유지한다.

명시적 hard-live 검증은 아래처럼 별도로 실행한다. `P27_HARD_LIVE_GATE=1` 상태에서 PPM profile/env 누락, template-only selected manifest, PPM 접근 실패, PLF fallback 은 skip 이 아니라 blocker failure 다.
Chakra/legacy proxy 경로에서 `python-tds` 기본 negotiation 이 차단되면 로컬 host-run에 한해 `MSSQL_METADATA_TDS_VERSION=7.0` 을 함께 지정한다.

```bash
P27_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 MSSQL_METADATA_CONNECT_TIMEOUT_SECONDS=20 make test PYTEST_ARGS="tests/eval/test_p27_dependency_evidence_hard_live_gate.py"
```
