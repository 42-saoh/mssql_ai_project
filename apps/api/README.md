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
- `GET /api/v1/registry/versions`

## Platform DB persistence

API repository 는 로컬 Platform MSSQL DB를 기준으로 동작한다. `.env`에서 아래를 설정한 뒤
`make run-api`로 실행한다.

- `PLATFORM_DB_HOST`, `PLATFORM_DB_PORT`, `PLATFORM_DB_USER`, `PLATFORM_DB_PASSWORD`, `PLATFORM_DB_NAME`
- `PLATFORM_DB_REQUESTER_LOGIN`

이 adapter 는 `db/schema/` DDL을 자동 적용하지 않고, source DB 업무 row 조회도 수행하지 않는다.
수동으로 schema를 적용하고 `AUTH_USERS`, `CORE_DB_PROFILES` 기준 행을 준비한 로컬 DB에서만
request/job/metadata/artifact/validation/approval/audit 기록을 저장하고 다시 읽는다.

## 남은 Blockers

1. 운영 auth/RBAC enforcement 는 인증 주체와 role source 가 확정된 뒤 활성화한다.
2. 현재 metadata 수집은 MSSQL MCP tool registry boundary 의 fixture-backed adapter 를 사용한다.
3. OpenAI key 기반 generation provider wiring 은 P05 API/workflow slice 밖이다.
4. OpenAPI approval decision 과 DDL approval enum 은 API 내부 mapping helper 로 고정했다.
5. validation status `PASSED/FAILED/REVIEW_REQUIRED` 와 DDL `PASS/FAIL` 은 API 내부 mapping helper 로 고정했다.
