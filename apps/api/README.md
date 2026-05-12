# apps/api

중앙 통합형 Agent 플랫폼의 API/BFF 와 workflow 시작점을 두는 디렉터리다.

## 현재 포함

- `api_app/main.py`
- `api_app/routes/health.py`
- `api_app/routes/jobs.py`
- `api_app/routes/requests.py`
- `api_app/routes/artifacts.py`
- `api_app/routes/approvals.py`
- `api_app/routes/metadata.py`
- `api_app/routes/registry.py`
- MSSQL platform DB backed request/job/artifact workflow repository

## 현재 endpoint slice

- `GET /health`
- `POST /api/v1/requests/sp-analysis`
- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{jobId}`
- `GET /api/v1/jobs/{jobId}/agent-runs`
- `GET /api/v1/jobs/{jobId}/artifacts`
- `GET /api/v1/artifacts/{artifactId}`
- `GET /api/v1/artifacts/{artifactId}/validation/latest`
- `POST /api/v1/artifacts/{artifactId}/validation`
- `POST /api/v1/artifacts/{artifactId}/approval-decisions`
- `GET /api/v1/metadata/db-profiles`
- `GET /api/v1/metadata/tools`
- `POST /api/v1/metadata/tools/{toolName}/invoke`
- `GET /api/v1/metadata/search`
- `GET /api/v1/registry/versions`

`GET /api/v1/metadata/tools` returns a safe read-only catalog summary. P27
dependency evidence tools (`get_dependency_closure`,
`resolve_dependency_reference`) appear there when active and carry
`invokable=true`. P28 adds `POST /api/v1/metadata/tools/{toolName}/invoke` for
those two tools only. P29 consumes that route from the Web diagnostic UI and the
workflow dependency-evidence path. The API still does not expose input schemas,
secrets, persisted artifact type changes, or DB schema changes.

## P09 workflow hardening notes

- `POST /api/v1/requests/sp-analysis` accepts `Idempotency-Key`. The same key with
  the same normalized request replays the same request/job; the same key with a different
  payload returns `IDEMPOTENCY_CONFLICT`.
- All routes accept `X-Correlation-ID` and return `X-Correlation-ID`. If the request omits
  it, the API generates one for response tracing and audit payloads.
- Error bodies use `{detail, code}` for validation errors, missing resources, dependency
  blockers, and workflow/idempotency conflicts.
- Artifact listing is internally bounded and stable-ordered. A public pagination contract
  remains an OpenAPI coordination item, so no query/body schema was added in P09.
- P25 default workflow stops at `VALIDATION_COMPLETE` after validation. Artifacts remain
  draft/validated outputs; review-pending, approved, and rejected states are retained only
  for deferred approval compatibility. Publish transitions remain blocked.

## P13 validation / approval / audit notes

- P25 keeps this approval API/server code as a deferred capability, but the default workflow,
  Web UI, and smoke path do not call it.
- Approval decisions require the latest artifact validation report. If callers omit
  `validationReportId`, the workflow binds the latest report internally; stale report ids
  are rejected.
- Reviewer checklist and validation summary details are persisted in the existing approval
  checklist JSON storage and are not added to the public response shape.
- Audit payloads carry stage, actor, target ref, compact refs, and correlation id. Platform DB
  audit persistence uses the existing `TRC_ID` column and does not require schema changes.
- Publish/export gate checks continue to fail unless validation is `PASSED` and the human
  decision is `APPROVE`; no publish/export endpoint is exposed in this API slice.

## P18B Web HTTP adapter smoke

Web HTTP adapter release evidence 는 fixture-backed local API route surface 를 대상으로
아래 명령으로 검증한다.

```bash
python3 tests/e2e/web_http_adapter_smoke.py
```

이 runner 는 FastAPI app 을 local HTTP 서버로 기동하고 `apps/web` 의
`smoke:http-adapter` command 를 실행해 request/job/artifact/validation/metadata/registry
경로가 `PortalApi` HTTP client 를 통해 호출되는지 확인한다. Production auth/RBAC source 는
verified OIDC/JWT identity 와 PLF auth table role lookup 이다. P19 는 `AUTH_RBAC_ENFORCEMENT=1`
일 때 validation/deferred approval route 에 401/403 enforcement 와 unauthorized negative tests 를
추가했다. Live IdP/JWKS 와 운영 PLF role membership 검증은
`AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED` future hardening item 으로 deferred 상태이며,
controlled conditional open 의 active productization blocker 로 취급하지 않는다.

## P20 auth/RBAC live gate

P20 live gate 는 명시적으로 `AUTH_RBAC_LIVE_GATE=1` 을 켠 경우에만 approved test
IdP/JWKS 와 PLF role lookup 을 검증한다. 기본 `make test` 와 `tests/eval` 실행은
fixture-first 로 유지하며 IdP/JWKS 또는 PLF 에 접근하지 않는다. 이 gate 는
production-grade enterprise Auth/RBAC 를 주장하기 전 필요한 optional future hardening
검증이며, 현재 controlled conditional open 의 blocker 는 아니다.

필수 환경변수는 루트 `.env` 또는 승인된 secret manager 에서 주입한다. token 값은 저장소,
문서, fixture, 테스트 snapshot, 채팅 로그에 남기지 않는다.

- `AUTH_RBAC_LIVE_GATE=1`
- `AUTH_RBAC_ENFORCEMENT=1`
- `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL`
- `OIDC_REVIEWER_BEARER_TOKEN`, `OIDC_USER_BEARER_TOKEN`
- 기존 `PLATFORM_DB_HOST`, `PLATFORM_DB_PORT`, `PLATFORM_DB_USER`,
  `PLATFORM_DB_PASSWORD`, `PLATFORM_DB_NAME`

read-only helper:

```bash
python3 apps/api/scripts/auth_rbac_live_probe.py
```

pytest gate:

```bash
AUTH_RBAC_LIVE_GATE=1 AUTH_RBAC_ENFORCEMENT=1 make test PYTEST_ARGS="tests/eval/test_p20_auth_rbac_live_gate.py"
```

helper 는 `OidcJwtVerifier` 와 `MssqlPlatformRepository.resolve_actor_roles()` 경계만
사용한다. API validation/deferred approval route 를 호출하지 않고 workflow write, approval write,
validation write, audit write, publish/export, DDL/DML, procedure execution, row data 조회를
만들지 않는다. 출력은 pass/fail, role category, blocker code, redacted summary 로 제한한다.
필수 live env 가 없거나 live 검증이 실패하면 deferred prerequisite failure 로 보고하며,
fixture-backed P19 401/403 enforcement 결과를 production-ready Auth/RBAC 로 과장하지 않는다.

### Assisted login

Playwright MCP 는 approved non-production/test IdP 또는 dev portal 에서 사람이 로그인하도록
돕는 preflight 에만 사용할 수 있다. 사용자가 credentials/MFA 를 처리하고, 발급된 bearer
token 은 로컬 `.env` 또는 승인된 secret manager 에 직접 주입한다.

금지 사항:

- arbitrary browser JavaScript 로 token 을 추출
- localStorage scraping 또는 cookie scraping
- storage-state files 저장
- token-bearing screenshots, traces, recordings 생성 또는 커밋
- chat-pasted secrets

이 gate 가 성공하기 전까지 `AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED` 는 deferred
future hardening item 으로 유지된다. Controlled conditional open 은 가능하지만
production-grade enterprise Auth/RBAC 또는 `production_ready: true` 로 주장하지 않는다.

## P21 no-mock portal live gate

P21 은 Web runtime/default path 를 HTTP API 로 고정하고, PLF platform DB 와 PPM read-only
metadata 를 controlled live portal 의 필수 조건으로 둔다. 기본 테스트는 fixture-first 로
유지하며 PLF/PPM live access 를 초기화하지 않고 skip 을 기록한다. 아래 gate 를 켜면 missing
PLF/PPM 은 skip 이 아니라 blocker failure 다.

```bash
P21_LIVE_PORTAL_GATE=1 make test PYTEST_ARGS="tests/eval/test_p21_live_portal_no_mock_gate.py"
```

필수 환경변수:

- `P21_LIVE_PORTAL_GATE=1`
- `PLATFORM_DB_HOST`, `PLATFORM_DB_PORT`, `PLATFORM_DB_USER`,
  `PLATFORM_DB_PASSWORD`, `PLATFORM_DB_NAME`
- `MSSQL_ENABLE_LIVE_METADATA=1`
- `MSSQL_METADATA_HOST`, `MSSQL_METADATA_PORT`, `MSSQL_METADATA_USER`,
  `MSSQL_METADATA_PASSWORD`, `MSSQL_METADATA_PROFILE_FILE`

helper:

```bash
python3.14 apps/api/scripts/p21_live_portal_probe.py
```

이 gate 는 PPM metadata search, PLF workflow submit, explicit validation 을 검증한다.
Workflow/validation/audit write 는 PLF core platform flow 로만
허용된다. Row data, procedure execution, business DB DDL/DML, publish/export/deployment,
PLF fallback for PPM, token/secret/raw claims 저장은 계속 금지다.

## P22 OpenAI LLM agent runtime

Remote LLM execution defaults to official OpenAI. Set `LLM_REMOTE_PROVIDER=pgpt` to use the private P-GPT `/v1/responses` contract; configure `OPENAI_BASE_URL=http://<host>/gpgpta01-gpt` or exact `OPENAI_RESPONSES_URL`, plus optional `PGPT_MODEL_ANALYSIS` / `PGPT_MODEL_FAST_TEST`.

`POST /api/v1/requests/sp-analysis` 는 P26 기준 high-quality hybrid LLM semantic analysis 를 기본값으로 사용한다.

- `useLlmAnalysis`: 기본 `true`; deterministic metadata/static analysis 이후 LLM semantic enrichment 실행
- `useAiToolOrchestration`: 기본 `true`; `useLlmAnalysis=false` 이면 자동 비활성화되며, LLM planner 가
  필요한 read-only MCP metadata tool 을 제안하고 workflow 가 내부 registry/policy gate 로만 실행
- `llmProfileId`: 기본 `openai_sp_semantic_analysis`; `openai_fast_test` 는 수동/평가 선택지
- `allowSpDefinitionToModel`: 기본 `true`; SP definition 원문은 transient model input 으로만 허용

기본 실행은 `FakeModelGateway` 를 사용하므로 외부 OpenAI API 를 호출하지 않는다. Remote 실행은
`LLM_ENABLE_REMOTE=1`, `LLM_ALLOW_SP_TEXT=1`, `OPENAI_API_KEY` 가 준비된 경우에만 가능하다.
semantic analysis 기본 모델은 `gpt-5.5` 이며 optional live confidence testing 에서는 `OPENAI_MODEL_ANALYSIS` 로 바꿀 수 있다. fast/test profile 기본 모델은 `gpt-5-nano` 이며 `OPENAI_MODEL_FAST_TEST` 로 수동 평가 실행 모델을 바꿀 수 있다.
내부 runtime 은 요청 target 을 SP task 로 감싼 뒤 bounded metadata tool planning, deterministic evidence digest, business rule extraction, conversion readiness, migration guide insights, evidence critic, optional repair staged calls 를 수행한다. 단일 API 요청 shape 는 그대로이며, batch API 는 추가하지 않는다. 여러 SP task 실행 경로에서는 `LLM_SP_CONCURRENCY` 기본값 `2` 로 fan-out 을 제한한다.

`GET /api/v1/jobs/{jobId}/agent-runs` 는 sanitized trace summary 만 반환한다. 응답에는
schema-valid structured output, provider/model/profile, prompt/schema version, input/prompt/output
hash, token usage, latency, status, optional `componentInvocations` 가 포함된다. raw prompt, raw SP definition, raw OpenAI response text 는 저장하거나 반환하지 않는다.
AI-selected metadata tool component 는 toolName 과 sanitized argument/output hash 중심으로만 저장하며,
raw arguments, raw definition text, row data, secret-like fields 는 저장하지 않는다.

Platform DB 를 사용할 경우 `db/schema/ai_agent_platform_schema_v3_agent_runtime.sql` 을 운영자가
수동 적용해야 한다. API 는 해당 DDL 을 자동 실행하지 않는다.

## Platform DB persistence

API repository 는 로컬 Platform MSSQL DB를 기준으로 동작한다. `.env`에서 아래를 설정한 뒤
`make run-api`로 실행한다.

- `PLATFORM_DB_HOST`, `PLATFORM_DB_PORT`, `PLATFORM_DB_USER`, `PLATFORM_DB_PASSWORD`, `PLATFORM_DB_NAME`
- `PLATFORM_DB_REQUESTER_LOGIN`

이 adapter 는 `db/schema/` DDL을 자동 적용하지 않고, source DB 업무 row 조회도 수행하지 않는다.
수동으로 schema를 적용하고 `AUTH_USERS`, `CORE_DB_PROFILES` 기준 행을 준비한 로컬 DB에서만
request/job/metadata/artifact/validation/deferred approval/audit 기록을 저장하고 다시 읽는다.

## Repository adapter boundary

- `api_app.platform_db.MssqlPlatformRepository` 는 externally managed PLF schema 를 사용하는
  platform persistence adapter 다. DDL 자동 적용, row-data 조회, procedure 실행은 수행하지 않는다.
- `api_app.auth` 는 `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL` 을 사용해 bearer JWT 를
  검증하고, PLF role membership 으로 effective authorization 을 결정한다.
- `api_app.memory_repository.MemoryWorkflowRepository` 는 fixture-first 테스트와 local demo 용
  in-memory/stub adapter 다. Platform DB 저장소와 같은 workflow 상태 전이, validation/deferred approval
  mapping, audit payload shape 를 유지하되 production persistence 로 사용하지 않는다.

## Metadata search

- `GET /api/v1/metadata/search` 는 승인된 OpenAPI contract 에 맞춘 read-only metadata search
  endpoint 다. MCP tool catalog 와 Web UI 는 이 P09 slice 에서 수정하지 않았다.
- API 는 MSSQL MCP registry boundary 를 통해 metadata inventory tool 을 호출한다. 기본 테스트
  모드는 fixture-backed repository 를 사용하고, `MSSQL_ENABLE_LIVE_METADATA=1` 일 때는
  env-gated live metadata repository 를 사용한다.
- 응답은 object identity, source profile/database, snapshot/evidence refs, caveats,
  `reviewRequired`, blockers 로 제한한다. Row data, SQL definition text, procedure execution,
  DDL/DML 결과는 반환하지 않는다.
- PPM manifest 가 `template_only` 이면 실제 object name 을 반환하지 않고
  `PPM_MANIFEST_TEMPLATE_ONLY` blocker 와 빈 결과를 반환한다.
- required MCP inventory/search capability 가 없으면 `METADATA_SEARCH_MCP_TOOL_MISSING`,
  PPM 접근 실패나 live metadata unavailable 은 해당 MCP blocker code 를 PLF fallback 없이 반환한다.

## Metadata analysis

- `POST /api/v1/metadata/analyze` 는 response-only bounded AI-MCP metadata analysis endpoint 다.
  요청은 `dbProfileId` 와 `query` 또는 단일 `target` 중 하나를 받으며, `options.useLlmAnalysis=true`,
  `options.useAiToolOrchestration=true`, `options.maxTargets=3` 을 기본값으로 사용한다.
- 기존 `GET /api/v1/metadata/search` 는 LLM 호출 없이 deterministic search 로 유지한다. Analyze API 는
  baseline identity/evidence 를 만든 뒤 LLM planner 가 필요한 active/read-only MCP tool 을 strict JSON
  plan 으로 제안하게 하고, 실제 실행은 내부 registry/policy gate 로만 수행한다.
- public `/metadata/tools/{toolName}/invoke` allowlist 는 확장하지 않는다. `get_table_schema` 같은 tool 은
  analyze API 내부 orchestration 에서만 실행될 수 있다.
- 응답은 sanitized `aiToolEvidence`, `deterministicFacts`, `mcp.<toolName>.<hash>` fact id,
  `objectInsights`, `reviewMarkers`, caveats 로 제한한다. v1 은 DB migration, persisted artifact,
  workflow state transition 을 추가하지 않는다.

## Metadata tool invocation

P29 consumes this P28 route from the Web diagnostic route
`/metadata/dependencies` and from workflow metadata collection. Workflow only
auto-invokes `get_dependency_closure` for PROCEDURE targets, stores a sanitized
`dependencyEvidence` digest, merges dependency evidence refs into generation
context and draft artifact evidence, and keeps `resolve_dependency_reference`
manual-only. PPM metadata unavailability remains a blocker with no PLF fallback.
P29B confirms this as the persisted boundary: no DB migration, no new persisted
artifact type, and no workflow state transition is added for dependency evidence.

- `POST /api/v1/metadata/tools/{toolName}/invoke` 는 P28 safe fixture-first API slice 로,
  `get_dependency_closure` 와 `resolve_dependency_reference` 만 public allowlist 로 호출한다.
- 요청 body 는 `{"arguments": {...}}` 형태만 허용하고, 실제 검증과 실행은 MSSQL MCP registry
  boundary 를 통한다. free-form SQL/write-capable argument, row data, procedure execution,
  business DB DDL/DML, raw definition storage, PPM-to-PLF fallback 은 계속 금지한다.
- 성공 응답은 `ok`, `toolName`, `dbProfileId`, `snapshotId`, `collectedAt`, `evidenceRefs`,
  `data` envelope 로 제한한다. 오류 응답은 기존 API 표준인 `{detail, code}` 를 유지한다.

## 남은 리스크와 Future Hardening

1. 운영 auth/RBAC source 와 fixture-backed enforcement 는 문서화/구현되었지만, P20 live gate 가 approved IdP/JWKS 와 PLF role membership 을 통과하기 전까지 `AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED` 는 deferred future hardening item 으로 유지된다.
2. Metadata search 의 live 실행은 `MSSQL_ENABLE_LIVE_METADATA=1` 과 외부 PPM/PLF 접근 설정에
   의존한다. 테스트 기본값은 fixture-backed repository 이지만 route 는 hardcoded mock 응답을
   반환하지 않는다.
3. OpenAI key 기반 generation provider wiring 은 P05 API/workflow slice 밖이다.
4. OpenAPI approval decision 과 DDL approval enum 은 API 내부 mapping helper 로 고정했다.
5. validation status `PASSED/FAILED/REVIEW_REQUIRED` 와 DDL `PASS/FAIL` 은 API 내부 mapping helper 로 고정했다.
