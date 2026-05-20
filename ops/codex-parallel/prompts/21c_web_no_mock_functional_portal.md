# P21C Web No-Mock Functional Portal

## 공통 운영 철학

- 현재 대화 요청과 실제 파일 구조를 최우선 기준으로 삼는다.
- P20 Auth/RBAC live IdP/JWKS wiring 은 deferred future hardening 으로 유지한다.
- `production_ready: false` 를 유지하고 full production-ready 로 과장하지 않는다.
- Web 은 runtime/default path 에서 mock adapter 를 사용하지 않는다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이며, missing PPM 을 PLF 로 대체하지 않는다.
- row data, procedure execution, DDL/DML, publish/export/deployment UI action 은 노출하지 않는다.
- P21A 의 Python 3.14 host+Docker baseline 을 현재 실행 기준으로 둔다.

## 목표

화면 목업과 demo id 흐름을 제거하고, Web 페이지가 실제 HTTP API/BFF 를 호출하는 controlled live portal 로 동작하게 한다.

## 읽어야 할 기준 파일

- `apps/web/**`
- `apps/api/README.md`
- `spec/openapi/ai_agent_platform_openapi_v1.yaml`
- `fixtures/eval/live_portal_no_mock_p21_v1.yaml`
- `tests/unit/web/**`
- `tests/e2e/**`
- `POLICY.md`

## 허용 수정 경로

- `apps/web/**`
- `tests/unit/web/**`
- `tests/e2e/**`
- `tests/contract/**`
- `docs/user-guide/**`
- `docs/integration-eval-status.md`

## 금지 경로

- `services/mssql-mcp/**`
- `packages/**`
- `db/schema/**`
- `spec/**` route/schema 변경은 P21B 에서만 수행
- demo ids 를 functional route 에 남기는 변경
- mock header 로 production Auth/RBAC 를 가장하는 변경
- token/secret/raw JWT claims 저장

## 구현 범위

- `PORTAL_API_MODE=http` 와 `PORTAL_API_BASE_URL` 을 app 사용의 필수 조건으로 둔다.
- `apps/web/lib/api/mock-adapter.ts` 는 runtime/default path 에 연결하지 않는다.
- P25 이후 functional Web pages 는 `/`, `/requests/new`, `/metadata/design`, `/jobs/[jobId]`, `/artifacts/[artifactId]` 로 유지하고 `/review/decision` 은 기본 UI 에서 제거한다.
- `job_demo_*`, `art_demo_*`, `approval_preview_*` 링크와 fallback 을 제거한다.
- `/requests/new` 는 API submit 후 실제 반환된 job id 로 redirect 한다.
- `/artifacts/[artifactId]` 는 page-load validation write 를 만들지 않고 latest validation 을 표시하며, run-validation 은 명시적 action 으로 둔다.
- Approval decision API 는 서버 compatibility 로 남기되 default Web flow 와 smoke path 에서 호출하지 않는다.
- PLF/PPM/live metadata prerequisites 가 없으면 dependency/configuration blocker 를 명확히 렌더링한다.

## 검증 명령

- `make test-web-smoke`
- `make test PYTEST_ARGS="tests/unit/web tests/contract/test_p21_no_mock_prompt_assets.py"`
- `P21_LIVE_PORTAL_GATE=1 make test PYTEST_ARGS="tests/eval/test_p21_live_portal_no_mock_gate.py"`

## Blocker 보고 기준

- Web 이 mock adapter 또는 demo ids 없이는 기능 페이지를 렌더링할 수 없음
- API base URL 미설정 상태를 blocker 로 표시하지 못함
- request/validation action 이 실제 API client 를 호출하지 않음
- default Web flow 또는 smoke path 가 approval decision API 를 호출함
- page-load validation write 가 남아 있음
- row data/procedure execution/DDL/DML/publish/export/deployment action 이 노출됨
