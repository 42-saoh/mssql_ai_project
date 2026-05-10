# apps/web

중앙 포털 UI 의 시작점이다. P21 기준 runtime/default path 는 no-mock HTTP API mode 이며,
`PORTAL_API_MODE=http` 와 `PORTAL_API_BASE_URL` 이 app 사용의 필수 조건이다.

## Routes

- `/` - 최근 jobs, PPM metadata search, draft artifact 목록 요약
- `/requests/new` - API `POST /api/v1/requests/sp-analysis` submit 후 실제 job id 로 redirect
- `/metadata/search` - read-only metadata identity/evidence search
- `/jobs/[jobId]` - 실제 job 상태와 draft artifact 목록
- `/artifacts/[artifactId]` - artifact preview 와 latest validation 표시
- `/review/decision` - API approval decision recording form

## API boundary

- `lib/api/portal-api.ts` 는 화면이 기대하는 API client 인터페이스다.
- `lib/api/http-client.ts` 는 runtime/default API adapter 다.
- `lib/api/client.ts` 는 `PORTAL_API_MODE=http` 와 `PORTAL_API_BASE_URL` 을 요구한다.
- runtime/default path 에 mock adapter 또는 demo id fallback 은 없다.
- `lib/api/errors.ts` 는 API `{code, detail}` error body 를 보존해 PLF/PPM/config blocker 를
  화면에 표시한다.
- `lib/pilot-manifest.ts` 는 PPM manifest 가 `live_metadata` 인 경우에만 sample object
  identities 를 읽고, `template_only` 일 때는 실제 이름을 노출하지 않는다.

## P21 behavior

- `/requests/new` 는 mock draft job 이 아니라 API 가 반환한 job id 로 이동한다.
- `/artifacts/[artifactId]` 는 page-load 에 validation write 를 만들지 않는다.
  Latest validation 은 `GET /api/v1/artifacts/{artifactId}/validation/latest` 로 읽고,
  validation write 는 사용자가 `Run validation` 을 누를 때만 실행한다.
- `/review/decision` 은 preview-only 가 아니라
  `POST /api/v1/artifacts/{artifactId}/approval-decisions` 를 호출한다.
- PLF/PPM/API prerequisites 가 없으면 dependency blocker 를 렌더링한다.

현재 화면은 row data 조회, procedure execution, DDL/DML, publish/export, deployment,
production Auth/RBAC mock header 가장을 제공하지 않는다. P20 Auth/RBAC live IdP wiring 은
future hardening 으로 남아 있으며 `production_ready: false` 를 유지한다.
