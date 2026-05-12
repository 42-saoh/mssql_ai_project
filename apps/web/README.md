# apps/web

중앙 포털 UI 의 시작점이다. P21 기준 runtime/default path 는 no-mock HTTP API mode 이며,
`PORTAL_API_MODE=http` 와 `PORTAL_API_BASE_URL` 이 app 사용의 필수 조건이다.

## Routes

- `/` - 최근 jobs, PPM metadata search, draft artifact 목록 요약
- `/requests/new` - API `POST /api/v1/requests/sp-analysis` submit 후 실제 job id 로 redirect
- `/metadata/search` - read-only metadata identity/evidence search and explicit metadata analyze action
- `/metadata/dependencies` - safe dependency closure/reference diagnostics
- `/jobs/[jobId]` - 실제 job 상태와 draft artifact 목록
- `/artifacts/[artifactId]` - artifact preview 와 latest validation 표시

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
- PLF/PPM/API prerequisites 가 없으면 dependency blocker 를 렌더링한다.

## P25 behavior

- `/review/decision` 화면과 approval CTA 는 기본 Web UI 에서 제거되었고 직접 접근은 404 로 처리한다.
- Validation 결과의 `REVIEW_REQUIRED` 는 사람 승인 요청이 아니라 evidence caveat 로 표시한다.
- Approval API/server code 는 추후 재활성화를 위한 deferred capability 로 남지만 Web API client 와
  smoke path 는 호출하지 않는다.

## P29 behavior

- `/metadata/dependencies` is a read-only diagnostic surface for
  `get_dependency_closure` and `resolve_dependency_reference`.
- The page uses `/api/v1/metadata/tools` only for `invokable` status and never
  renders MCP input schemas.
- The forms accept only structured metadata identifiers, `maxDepth`, and
  `includeReviewRequired`; there are no free-form SQL, row data, procedure
  execution, DDL/DML, raw definition, or secret fields.
- Results render the sanitized invocation envelope: `snapshotId`, `collectedAt`,
  evidence refs, closure nodes/edges/unresolved references, candidates, and
  selected resolution.

## Metadata analysis behavior

- `/metadata/search` keeps deterministic search as the default page load. The `Analyze metadata`
  action calls `POST /api/v1/metadata/analyze` explicitly.
- The analysis panel renders response-only `summary`, `objectInsights`, `objectProfiles`,
  `insightGroups`, `dependencyGraph`, `dtoReadiness`, deterministic fact count, sanitized
  tool-call count, review markers, and caveats.
- The Web client does not expose MCP input schemas, raw definition text, row data, procedure
  execution, DDL/DML controls, or raw provider traces.

## P22 behavior

- `/requests/new` 는 P26 high-quality hybrid 기본값으로 LLM semantic analysis option 을 API
  `SPAnalysisOptions` 로 전송한다. 기본 선택은 semantic analysis profile, LLM analysis enabled,
  bounded AI metadata tool orchestration enabled, transient SP definition input allowed 이며
  fast/test profile 은 수동 선택지로만 남긴다.
- `/jobs/[jobId]` 는 `GET /api/v1/jobs/{jobId}/agent-runs` 로 sanitized LLM trace summary 를 읽어
  model, prompt/schema version, input/output hash, token usage, latency, status 를 표시한다.
- `/artifacts/[artifactId]` 는 artifact 의 job id 가 있을 때 같은 sanitized trace summary 를 표시한다.
- raw prompt, raw SP definition, raw OpenAI response text 는 Web API client type 과 화면에 없다.

현재 화면은 row data 조회, procedure execution, DDL/DML, publish/export, deployment,
production Auth/RBAC mock header 가장을 제공하지 않는다. P20 Auth/RBAC live IdP wiring 은
future hardening 으로 남아 있으며 `production_ready: false` 를 유지한다.
