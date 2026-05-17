# apps/web

Central portal UI for the MSSQL analysis platform. The Web app runs in no-mock HTTP mode: `PORTAL_API_MODE=http` and `PORTAL_API_BASE_URL` are required at runtime.

## Routes

- `/` - dashboard with recent analysis jobs, metadata search summary, and draft artifact links.
- `/requests/new` - submits single and batch SP analysis requests to the portal API, then links to accepted jobs.
- `/jobs` - recent analysis history with targetKey/target/profile/status/output filters and artifact preview links.
- `/jobs/[jobId]` - workflow status, sanitized LLM trace summary, knowledge assets, and draft artifacts.
- `/knowledge/assets/[assetId]` and `/knowledge/assets/[assetId]/versions/[versionId]/facts` - sanitized knowledge asset version and fact graph views.
- `/artifacts/[artifactId]` - artifact preview, copy/download controls, evidence refs, caveats, sanitized trace, and explicit validation trigger.
- `/metadata/search` - read-only metadata identity/evidence search plus client-side async metadata analysis.
- `/metadata/design` - chat-style metadata design run UI for durable table script previews and DTO_DRAFT previews.
- `/metadata/dependencies` - read-only dependency closure and reference resolver diagnostics.

## SP Request Progress

- The single SP request form submits with `runAsync=true`, receives a `jobId` immediately, and
  redirects to `/jobs/[jobId]` while the API runs the workflow in the background.
- `/jobs/[jobId]` shows `Estimated progress`, a status-based progress bar, and auto-refreshes every
  1.5 seconds while the job is active. The percentage is a visibility estimate, not exact work
  completion.
- Batch request submission keeps the existing accepted/rejected summary behavior.

## API Boundary

- `lib/api/portal-api.ts` defines the UI-facing portal API contract.
- `lib/api/http-client.ts` is the runtime HTTP adapter.
- `lib/api/client.ts` requires HTTP mode and API base URL; there is no mock adapter or demo id fallback.
- `lib/api/errors.ts` normalizes API `{code, detail}` blockers for UI display.
- `lib/pilot-manifest.ts` only reads live sample object identities when the pilot manifest is in `live_metadata` mode.

## Local Checks

- `pnpm --dir apps/web run test:smoke` runs the Web build smoke.
- `pnpm --dir apps/web run smoke:draft-download` verifies draft artifact filename mapping and the dependency-free ZIP writer.
- `pnpm --dir apps/web run smoke:http-adapter -- <api-base-url>` exercises the strict HTTP adapter against a running Portal API.

## Analysis History

- History rows, job detail, artifact preview, metadata profiles, and knowledge asset rows show the server-derived `targetKey` when available.
- `/jobs?targetKey=...` uses the public exact-match filter so users can paste a canonical key and find prior runs for the same root target.
- Job and artifact views include same-target history links. `targetRef` remains display text; `targetKey` is the stable lookup key.

## Metadata Search And Analysis

- Search stays server-rendered and calls `GET /api/v1/metadata/search`.
- `Analyze metadata` is a client-side async action. It calls the internal Web route `POST /api/metadata/analysis-runs`, which proxies public `POST /api/v1/metadata/analysis-runs`; the client then polls `GET /api/metadata/analysis-runs/{runId}` until the public run reaches `SUCCEEDED` or `FAILED`.
- The public analysis-run API uses durable platform storage when
  `db/schema/ai_agent_platform_schema_v7_metadata_analysis_runs.sql` has been manually applied.
  If that schema is missing, the page renders the API blocker instead of falling back to a mock or
  process-local run state.
- If a durable run is interrupted, the API background recovery worker reclaims queued or
  stale running metadata runs and the same polling UI continues until the run reaches a
  terminal `SUCCEEDED` or structured `FAILED` result.
- The action defaults `maxTargets` to `1` and clamps user input to `1-5`.
- While analysis is running, the page shows a disabled button, `분석 중` elapsed time, and any timeout/API blocker on the same screen instead of holding a full page navigation.
- The reusable metadata analysis panel renders summary, facts/tool metrics, object profiles, insight groups, dependency graph, DTO readiness, knowledge assets, evidence caveats, and caveats.

## Metadata Design Chat

- `/metadata/design` submits natural-language field, description, and table hints to the Web proxy `POST /api/metadata/design-runs`, which calls public `POST /api/v1/metadata/design-runs`.
- The client polls `GET /api/metadata/design-runs/{runId}` and can reopen a durable thread with `GET /api/metadata/design-conversations/{conversationId}`.
- Results render related metadata candidates, standardization mappings, a `createTableScriptPreview`, and a non-persisted `DTO_DRAFT` preview stored only in the design run result JSON.
- SQL and Java downloads are client Blob previews. They do not use workflow artifact storage, artifact download helpers, source repository writes, deploy, publish, execute, or apply flows.
- The page invokes no row-data tools and never renders raw prompts, raw provider responses, full SQL/SP definitions, procedure execution output, secrets, or apply controls.

## Dependency Diagnostics

- `/metadata/dependencies` defaults to the PPM live-safe profile and sample:
  - profile `ppm`
  - closure target `dbo.GetInspItemsCd`, `PROCEDURE`, `maxDepth=2`
  - resolver source `dbo.GetInspItemsCd`
  - resolver referenced object `dbo.PEX_INSP_ITEMS`
- The page invokes only read-only metadata tools: `get_dependency_closure` and `resolve_dependency_reference`.
- The UI never renders MCP input schemas, raw SQL, row data, procedure execution, raw definition text, DDL/DML apply controls, deploy, publish, or approval actions.

## Draft-Only Behavior

- The product flow is request -> metadata -> analysis -> generation -> validation -> `VALIDATION_COMPLETE`.
- `REVIEW_REQUIRED` remains a machine status/evidence caveat, not a human review CTA. User-facing copy renders it as `근거 보강 필요` or `Evidence caveat`.
- `/review/decision` is not implemented in Web.
- Validation writes only happen when the user explicitly clicks `Run validation`; page load reads the latest validation report.

## Knowledge Asset Behavior

- `/jobs/[jobId]` reads `GET /api/v1/jobs/{jobId}/knowledge-assets` and renders safe summaries plus Web asset/fact graph links.
- `/metadata/search` renders metadata analysis `knowledgeAssets[]` summaries in the reusable analysis panel.
- The Web client includes sanitized knowledge export support, but does not render raw fact payloads, raw metadata payloads, provider traces, row data, or raw SQL.
- Draft artifact downloads are Web-internal convenience routes backed by existing sanitized artifact preview APIs. Single artifact files and job-level ZIP bundles are draft-only and do not add publish/deploy/execute/apply behavior.
