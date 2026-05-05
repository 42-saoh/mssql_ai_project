# apps/web

중앙 포털 UI 의 시작점이다. 현재 shell 은 Next.js App Router 기반으로 동작하며,
P05 API 연결 전까지 OpenAPI skeleton 에 맞춘 mock adapter 를 기본 데이터 소스로 사용한다.

## Routes

- `/` - 중앙 포털 요약, mock job, draft artifact 목록
- `/requests/new` - PPM pilot manifest 기반 SP 분석 요청 form 초안
- `/metadata/search` - read-only metadata identity/evidence search
- `/jobs/job_demo_review_pending` - job 상태와 validation/review gate 흐름
- `/jobs/job_demo_failed_blocker` - PPM dependency blocker/failure 상태 예시
- `/artifacts/art_demo_sp_analysis` - artifact preview, evidence refs, validation checklist
- `/review/decision` - approval decision payload preview; publish/deploy 미제공

## API boundary

- `lib/api/portal-api.ts` 는 화면이 기대하는 API client 인터페이스다.
- `lib/api/mock-adapter.ts` 는 현재 shell 의 기본 데이터 소스다.
- `lib/api/http-client.ts` 는 이후 API/BFF 가 준비되면 같은 인터페이스로 연결할 경계다.
- `lib/pilot-manifest.ts` 는 PPM manifest 가 `live_metadata` 인 경우에만 sample object
  identities 를 읽고, `template_only` 일 때는 실제 이름을 노출하지 않는다.

기본값은 mock 이며, P05 API 가 준비되면 서버 환경에서 `PORTAL_API_MODE=http` 와
`PORTAL_API_BASE_URL` 을 지정해 HTTP client 로 전환할 수 있다.

현재 화면은 실제 DB 조회, DDL 실행, publish, 승인 확정 호출을 제공하지 않는다.
