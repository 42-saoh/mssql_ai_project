# apps/api

중앙 통합형 Agent 플랫폼의 API/BFF, workflow, approval 시작점을 두는 디렉터리다.

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
- `GET /api/v1/jobs/{jobId}`
- `GET /api/v1/jobs/{jobId}/artifacts`
- `GET /api/v1/artifacts/{artifactId}`
- `POST /api/v1/artifacts/{artifactId}/validation`
- `POST /api/v1/artifacts/{artifactId}/approval-decisions`
- `GET /api/v1/metadata/db-profiles`
- `GET /api/v1/metadata/tools`
- `GET /api/v1/metadata/search`
- `GET /api/v1/registry/versions`

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
- P09 still has no publish route; artifacts may be draft, validated, review-pending,
  approved, or rejected, but this slice blocks publish transitions.

## P13 validation / approval / audit notes

- Approval decisions require the latest artifact validation report. If callers omit
  `validationReportId`, the workflow binds the latest report internally; stale report ids
  are rejected.
- Reviewer checklist and validation summary details are persisted in the existing approval
  checklist JSON storage and are not added to the public response shape.
- Audit payloads carry stage, actor, target ref, compact refs, and correlation id. Platform DB
  audit persistence uses the existing `TRC_ID` column and does not require schema changes.
- Publish/export gate checks continue to fail unless validation is `PASSED` and the human
  decision is `APPROVE`; no publish/export endpoint is exposed in this API slice.

## Platform DB persistence

API repository 는 로컬 Platform MSSQL DB를 기준으로 동작한다. `.env`에서 아래를 설정한 뒤
`make run-api`로 실행한다.

- `PLATFORM_DB_HOST`, `PLATFORM_DB_PORT`, `PLATFORM_DB_USER`, `PLATFORM_DB_PASSWORD`, `PLATFORM_DB_NAME`
- `PLATFORM_DB_REQUESTER_LOGIN`

이 adapter 는 `db/schema/` DDL을 자동 적용하지 않고, source DB 업무 row 조회도 수행하지 않는다.
수동으로 schema를 적용하고 `AUTH_USERS`, `CORE_DB_PROFILES` 기준 행을 준비한 로컬 DB에서만
request/job/metadata/artifact/validation/approval/audit 기록을 저장하고 다시 읽는다.

## Repository adapter boundary

- `api_app.platform_db.MssqlPlatformRepository` 는 externally managed PLF schema 를 사용하는
  platform persistence adapter 다. DDL 자동 적용, row-data 조회, procedure 실행은 수행하지 않는다.
- `api_app.memory_repository.MemoryWorkflowRepository` 는 fixture-first 테스트와 local demo 용
  in-memory/stub adapter 다. Platform DB 저장소와 같은 workflow 상태 전이, validation/approval
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

## 남은 Blockers

1. 운영 auth/RBAC enforcement 는 인증 주체와 role source 가 확정된 뒤 활성화한다.
2. Metadata search 의 live 실행은 `MSSQL_ENABLE_LIVE_METADATA=1` 과 외부 PPM/PLF 접근 설정에
   의존한다. 테스트 기본값은 fixture-backed repository 이지만 route 는 hardcoded mock 응답을
   반환하지 않는다.
3. OpenAI key 기반 generation provider wiring 은 P05 API/workflow slice 밖이다.
4. OpenAPI approval decision 과 DDL approval enum 은 API 내부 mapping helper 로 고정했다.
5. validation status `PASSED/FAILED/REVIEW_REQUIRED` 와 DDL `PASS/FAIL` 은 API 내부 mapping helper 로 고정했다.
