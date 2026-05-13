# Integration Eval Status

## Summary

P24C update: the generation package now renders the P24 migration guide section
taxonomy and scores the rendered `SP_ANALYSIS_DOC` plus `DEPENDENCY_REPORT`
artifact pair with a fixture-first evaluator. P24 remains `production_ready: false`;
there is still no new persisted artifact type, public API/schema change, live DB
access, raw prompt/SP/provider-response storage, or PPM-to-PLF fallback.

P27 adds fixture-first hardened dependency evidence tooling: `get_procedure_dependencies` now declares optional resolution confidence/evidence fields, while `get_dependency_closure` and `resolve_dependency_reference` are active read-only MCP tools with fixture/live repository handlers and safe API tool-summary exposure. P28 adds the safe API invocation endpoint for those two tools only. P29 adds the read-only Web diagnostic UI and workflow `get_dependency_closure` evidence wiring. P29B confirms the deferred boundary: no DB migration, persisted artifact type, or workflow state transition is introduced; dependency evidence remains a sanitized digest plus existing draft artifact evidence refs. An explicit `P27_HARD_LIVE_GATE=1` validates selected PPM dependency evidence when enabled. No default live gate, row-data access, raw definition storage, procedure execution, DDL/DML, or PLF fallback is introduced.

P06 adds fixture-first coverage for the implemented request → job → artifact → validation path. P25 changes the default workflow terminal state to `VALIDATION_COMPLETE` and disables the review decision UI while retaining the approval API/server code as a deferred capability. P15 adds a hard-live eval/ops gate for PPM metadata readiness, observability, security, and reproducibility. P16/P17D now record the scoped live pilot candidate as `CONDITIONAL_GO` after P17A dependency evidence, P17B passed validation, P17C human approval/audit binding, and P17D hard-live gates passed. P18A adds the minimal versioned `CanonicalAnalysisModel` contract and deterministic analysis mapping; P18B records local web HTTP adapter smoke evidence and documents production auth/RBAC source of truth; P19 adds fixture-backed validation/deferred approval enforcement with 401/403 negative tests. P21 adds the Python 3.14 baseline and no-mock portal contract where Web calls HTTP API and live use requires PLF plus read-only PPM. P22 adds the OpenAI LLM Agent Runtime behind a model gateway and no-raw-trace policy. P23 now has a split contract/prompt pack, simple/medium/complex synthetic fixtures, and a fixture-first `FakeModelGateway` scoring runner; the optional OpenAI live quality gate is confidence-only evidence, not a production readiness requirement. P24 now has contract assets, sanitized guide-quality fixtures, and P24C renderer/evaluator scoring over existing draft artifact types. The suite separates fixture-first baselines, optional-live evidence, hard-live blockers, conditional pilot evidence, deferred future hardening, and follow-up slices.

## Current Boundaries

| Area | Status | Notes |
|---|---|---|
| API workflow | implemented | FastAPI routes submit the request, create a job, generate draft artifacts, validate, and stop at `VALIDATION_COMPLETE`. Approval decision routes remain implemented as deferred compatibility but are outside the default P25 flow. |
| Metadata collection | fixture-first | Default path uses `fixtures/mcp/metadata_snapshot.json` through the MSSQL MCP registry boundary. |
| Metadata profile | implemented | `master` is the default metadata profile; `plf` remains available for the platform DB profile. |
| Web portal | no-mock HTTP runtime | P21 default runtime requires explicit `PORTAL_API_MODE=http` and `PORTAL_API_BASE_URL`; missing API/PLF/PPM prerequisites render API `{code, detail}` blockers instead of mock adapter or demo ids. P25 removes the review decision page and approval CTA from the default UI. |
| Live MSSQL | explicit hard-live for P15 eval | Default eval is fixture-first. P15 live metadata checks run only with `P15_HARD_LIVE_GATE=1`; then `MSSQL_ENABLE_LIVE_METADATA=1`, `dbProfileId=ppm`, source database `PPM`, and read-only metadata permissions are required. Missing live PPM access is a blocker, not a skip. |
| Pilot release readiness | conditional scoped candidate | P17D records live pilot release as `CONDITIONAL_GO` only for the draft-only scoped candidate. This does not make the platform production-ready and does not authorize publish/export, DDL/DML, row-data access, procedure execution, deployment, or PLF fallback. |
| P18/P19 productization readiness | conditional open | P18A canonical contract closure, P18B local HTTP adapter smoke, production auth/RBAC source documentation, and P19 fixture-backed enforcement are covered. Live IdP/JWKS and PLF role lookup wiring remain deferred future hardening before any production-grade enterprise Auth/RBAC claim. |
| P21 live portal | explicit live gate | Default eval skips without PLF/PPM access. `P21_LIVE_PORTAL_GATE=1` requires PLF workflow repository and read-only PPM metadata access. Missing env is blocker failure, not skip, and does not imply `production_ready: true`. |
| P22 LLM runtime | implemented with gates | Default tests use `FakeModelGateway`; remote OpenAI calls require `LLM_ENABLE_REMOTE=1`, `LLM_ALLOW_SP_TEXT=1`, and `OPENAI_API_KEY`. Stored traces contain hashes, model/profile/token/latency/status summaries only, not raw prompt, SP definition, or provider response text. |
| P23 LLM quality eval | fixture-first scored | `spec/eval/p23_llm_sp_analysis_quality_contract.yaml` and `fixtures/eval/llm_sp_analysis_quality_p23_v1.yaml` define and author simple/medium/complex synthetic quality eval fixtures. `tests/eval/test_p23_llm_sp_analysis_quality.py` validates schema, deterministic evidence binding, fake-gateway execution with `openai_fast_test`, no-raw trace storage, no PPM-to-PLF fallback, and P23C/P26 quality scoring. Optional live quality gate uses high-quality `openai_sp_semantic_analysis` and `OPENAI_MODEL_ANALYSIS`; `openai_fast_test` still defaults to `gpt-5-nano` with `OPENAI_MODEL_FAST_TEST` for manual fast/test runs. Optional live output is a confidence signal only; current status remains `production_ready: false`. |
| P24 migration guide quality | fixture-first rendered/scored | `SP_ANALYSIS_DOC` and `DEPENDENCY_REPORT` render P24 guide sections from sanitized fixture facts, and `evaluate_p24_migration_guide_quality` scores the rendered artifact pair. The gate validates required section coverage, evidence-linked claims, DML matrix coverage, branch/call-flow coverage, `REVIEW_REQUIRED` unsupported claims, storage safety, PPM target context, no PLF fallback, and `production_ready: false`. |
| P30/P31 metadata analysis | fixture-first analysis response | Metadata Analyze keeps search deterministic and runs bounded internal-only AI-MCP orchestration only inside `POST /api/v1/metadata/analyze`. P31 adds object profiles, grouped insights, dependency graph, DTO readiness, and `metadata.profile.*` facts without persisted artifacts or workflow state transition. P34 adds sanitized knowledge asset persistence on top. |
| P32 planner effectiveness | fixture-first plus optional live confidence | `aiToolEvidence.plannerMetrics` records sanitized planned/executed/blocked/failed/deduped counts, evidence utilization, and claim support rate. `tests/eval/test_p32_live_confidence_planner_effectiveness.py` is fixture-first by default; `P32_LIVE_CONFIDENCE_GATE=1` adds remote LLM plus live PPM metadata confidence only and does not imply `production_ready: true`. |
| P33 performance/scale | fixture-first process-local | Metadata MCP tool success responses are cached in a TTL/LRU process-local cache, tool evidence includes stable `contentHash`, planner metrics include cache hit/miss counts, and `POST /api/v1/requests/sp-analysis/batch` creates normal per-target jobs with duplicate/limit rejection. Workflow/MCP backpressure uses `WORKFLOW_BACKPRESSURE` and `MCP_BACKPRESSURE`; no DB migration, queue infra, row data, DDL/DML, or public MCP allowlist expansion is added. |
| P34 knowledge assetization | fixture-first versioned knowledge | SP workflow and Metadata Analyze default `persistKnowledge=true` materialize sanitized `SP_ANALYSIS`, `DEPENDENCY_EVIDENCE`, `METADATA_PROFILE`, `DTO_READINESS`, and `CANONICAL_ANALYSIS` assets where applicable. v5 DDL is manual-apply only, same `contentHash` reuses the current version, APIs expose summaries/facts/JSONL/GRAPH_JSON export, and no raw SP definition, SQL text, row data, secrets, raw prompt/provider trace, or production-ready claim is introduced. |
| P27 dependency evidence tooling | fixture-first hardened | `spec/eval/p27_dependency_evidence_tooling_contract.yaml` and the MCP catalog define active read-only dependency closure/resolution tools plus optional dependency resolution evidence fields. P28 safe API invocation, P29 Web diagnostics, and workflow closure evidence wiring are fixture-first enabled; persisted artifact type and DB schema changes remain deferred. Ambiguous/dynamic/unresolved/cross-server/caller-dependent references stay `REVIEW_REQUIRED`. Explicit hard-live evidence runs only with `P27_HARD_LIVE_GATE=1`. |
| Publish | follow-up | Publish gate helper exists, but no publish endpoint or automatic publish flow is implemented. |
| DDL | follow-up | DDL draft type exists; automatic DDL execution is forbidden and not implemented. |
| Row data | out of scope | No row-data read/write path is implemented or documented as supported. |

## Eval Assets

- `fixtures/eval/request.json`: sample OpenAPI-style request using `master.dbo.usp_GetOrderSummary`.
- `fixtures/eval/canonical_analysis_candidate.json`: sample contract-closed canonical payload with field-level `REVIEW_REQUIRED` analysis markers.
- `fixtures/eval/artifact_payloads.json`: expected stable workflow/artifact summary.
- `fixtures/eval/rubric.yaml`: thresholds for fixture parsing, review-required markers, evidence, forbidden states, and secret-like values.
- `fixtures/eval/eval_observability_security_ops_p15_v1.yaml`: P15 hard-live gate for PPM metadata smoke, quality metrics, latency budgets, correlation id, audit stage, redaction, and read-only DB permission checks.
- `fixtures/eval/pilot_release_readiness_p16_v1.yaml`: P16/P17D pilot release checklist, quality report, selected object evidence summary, P17B validation binding, P17C approval/audit status, P17D hard-live evidence, and go/no-go recommendation.
- `fixtures/eval/live_pilot_artifact_validation_p17_v1.yaml`: P17B draft-only live pilot artifact validation package with passed release-critical checks.
- `fixtures/eval/manual_approval_audit_p17_v1.yaml`: P17C human approval and audit binding for the P17B artifact set/version and validation report.
- `fixtures/eval/productization_gap_closure_p18_v1.yaml`: P18/P19 productization fixture recording P18A canonical closure, P18B HTTP adapter smoke evidence, production auth/RBAC source documentation, fixture-backed enforcement, and the deferred live wiring hardening item.
- `fixtures/eval/live_portal_no_mock_p21_v1.yaml`: P21 no-mock portal and Python 3.14 contract fixture recording required pages, HTTP-only Web boundary, PLF/PPM prerequisites, live gate blocker behavior, and `production_ready: false`.
- `fixtures/eval/llm_sp_analysis_quality_p23_v1.yaml`: P23B/P26 simple/medium/complex synthetic LLM-assisted SP semantic analysis quality fixtures, including deterministic facts, transient model input, golden semantic/guide/conversion outputs, high-quality semantic default posture with `OPENAI_MODEL_ANALYSIS` live override, `gpt-5-nano` fast/test default with `OPENAI_MODEL_FAST_TEST` manual override, `LLM_INFERENCE`, `REVIEW_REQUIRED`, no-raw-trace storage expectations, and `production_ready: false`.
- `fixtures/eval/sp_migration_guide_quality_p24_v1.yaml`: P24B-authored simple/medium/complex synthetic SP migration guide quality fixtures, including required section taxonomy, dependency inventory, DML matrix, branch call flow, phase/risk metrics, appendix mappings, evidence refs, unsupported claim `REVIEW_REQUIRED`, storage safety, `gpt-5-nano` fast/test default, `OPENAI_MODEL_FAST_TEST` optional live override, and `production_ready: false`.
- `fixtures/eval/live_confidence_planner_effectiveness_p32_v1.yaml`: P32 planner effectiveness and live confidence fixture, including duplicate/deduped planner requests, blocked unsafe args, under-utilized evidence, optional OpenAI+PPM live confidence, and `production_ready: false`.
- `fixtures/eval/performance_scale_p33_v1.yaml`: P33 performance/scale fixture, including cache hit reuse, stable fact hashes, batch duplicate/limit handling, live round reduction, backpressure signaling, no raw leakage, and `production_ready: false`.
- `fixtures/eval/knowledge_assetization_p34_v1.yaml`: P34 knowledge assetization fixture, including SP/metadata asset kinds, version reuse, fact graph export, v5 manual schema boundary, no raw leakage, and `production_ready: false`.
- `spec/eval/p23_llm_sp_analysis_quality_contract.yaml`: P23 quality contract that separates P23A contract assets, P23B fixture authoring, P23C fixture-first eval runner/scoring, and P23D readiness documentation.
- `spec/eval/p27_dependency_evidence_tooling_contract.yaml`: P27 fixture-first hardening contract for dependency evidence fields, active read-only MCP tools, P28 safe API invocation, P29 Web diagnostics and workflow evidence wiring, explicit hard-live gate, no-raw/no-row/no-fallback policy, and deferred persisted artifact/DB schema boundaries.

## Verification Scope

`make test PYTEST_ARGS="tests/e2e tests/eval"` verifies the default fixture-first/eval gate:

- request acceptance returns `VALIDATION_COMPLETE`
- job current step is `VALIDATE`
- persisted artifact types are generated instead of returning `JAVA_MYBATIS_DRAFT` as a storage type
- evidence and registry refs are present where implemented
- validation reports keep `REVIEW_REQUIRED` as an evidence caveat without turning default artifacts into review-pending UI work
- approval decision recording is retained in server compatibility tests only, not default e2e/Web smoke
- eval fixtures parse and match generated workflow summaries
- P15 hard-live fixture contract, metrics, redaction, permission-check schema, and blocker policy are valid
- P15 fixture-first workflow smoke remains deterministic and draft artifacts stay complete without publishing
- P16/P17D readiness fixtures and docs preserve P17A/P17B/P17C/P17D evidence, P18A canonical contract checks stay fixture-first, and the live release remains limited to scoped `CONDITIONAL_GO`
- P18B HTTP adapter smoke can be run with `python3.14 tests/e2e/web_http_adapter_smoke.py`; the dockerized python test suite may skip this smoke when node/pnpm are unavailable.
- P19 auth/RBAC enforcement is covered by `tests/integration/api/test_api_auth_rbac.py`, including 401, 403, reviewer success, and reviewer spoofing cases.
- P21 prompt/fixture/no-mock/Python 3.14 contracts are covered by `tests/contract/test_p21_no_mock_prompt_assets.py` and `tests/unit/web`; default `tests/eval/test_p21_live_portal_no_mock_gate.py` skips unless the live gate is explicitly enabled.
- P23/P26 LLM quality fixtures and scoring are covered by `tests/eval/test_p23_llm_sp_analysis_quality.py`; default test execution uses `FakeModelGateway`, while API/Web defaults now select high-quality semantic analysis, transient SP definition input, and the `openai_sp_semantic_analysis` profile for live execution. Optional live confidence uses `OPENAI_MODEL_ANALYSIS`; `openai_fast_test` still defaults to `gpt-5-nano` and may be overridden with `OPENAI_MODEL_FAST_TEST` for manual fast/test runs. A passing fixture-first report requires `semantic_recall >= 0.75`, `guide_conversion_recall >= 0.8`, `evidence_discipline >= 0.9`, `unreviewed_overclaims <= 0`, and `storage_safety_findings <= 0`.
- P24 migration guide quality is covered by `tests/eval/test_p24_sp_migration_guide_quality.py`; default execution renders fixture-first `SP_ANALYSIS_DOC` and `DEPENDENCY_REPORT` artifacts, then scores them without live OpenAI, PPM, PLF, web/API, or schema access. A passing fixture-first report requires complete section coverage, evidence-linked claim coverage, DML matrix coverage, branch/call-flow coverage, unsupported claim review markers, and zero storage safety findings.
- P27 dependency evidence tooling is covered by `tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py`, `tests/unit/test_mcp_catalog.py`, `tests/unit/mcp/test_tool_registry.py`, `tests/contract/mcp/test_tool_invocation_contract.py`, `tests/unit/api/test_metadata_service.py`, and `tests/integration/api/test_api_workflow_routes.py`; the checks keep the tools active/read-only/structured-only, verify fixture/mocked-live handler behavior, expose them only through metadata tool summary, and avoid default live PPM or OpenAI gates. `tests/eval/test_p27_dependency_evidence_hard_live_gate.py` is explicit hard-live coverage for approved PPM environments.

For P15 hard-live validation, run the same suite with `P15_HARD_LIVE_GATE=1` and live PPM read-only metadata access configured:

```bash
P15_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/e2e tests/eval"
```

In this explicit mode, P15 hard-live PPM metadata calls must return live evidence refs, source profile/database context, no raw definition text, no row-data shape, and latency within the current live gate budget. If `MSSQL_ENABLE_LIVE_METADATA` is disabled or PPM access/permissions are missing, the eval suite fails with the corresponding blocker and must not fall back to PLF.

For P16/P17D, `make test PYTEST_ARGS="tests/eval/test_p16_pilot_release_readiness.py"` verifies the release fixture and handoff docs. The broader default gate is `make test PYTEST_ARGS="tests/e2e tests/eval tests/contract"` plus web smoke and compileall. Live PPM claims additionally require the explicit P15 hard-live command above and the contract-inclusive hard-live command.

The full default suite remains fixture-first/reproducible. Tests that assert fixture snapshot ids or fixture-backed metadata search results pin `MSSQL_ENABLE_LIVE_METADATA=0`; P15 hard-live tests require `P15_HARD_LIVE_GATE=1` and must never fall back from PPM to PLF.

For P21 no-mock portal validation, the default eval asserts the disabled gate skips without
initializing PLF or PPM access. For controlled live validation:

```bash
P21_LIVE_PORTAL_GATE=1 make test PYTEST_ARGS="tests/eval/test_p21_live_portal_no_mock_gate.py"
```

This requires PLF `PLATFORM_DB_*` and PPM read-only metadata env. If either is missing, the gate fails with a prerequisite blocker and must not use fixture metadata or PLF fallback for PPM.

For P22 OpenAI runtime validation, default tests use fake model responses. The optional live smoke is:

```bash
LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1 make test PYTEST_ARGS="tests/eval/test_p22_openai_live_agent_gate.py"
```

For P23 fixture-first contract validation, run:

```bash
make test PYTEST_ARGS="tests/eval/test_p23_llm_sp_analysis_quality.py tests/contract/test_p23_llm_eval_contract_prompt_assets.py"
```

This checks the P23 contract, authored P23B fixture suite, manifest split tracks, prompt pack, deterministic evidence binding, P23C fixture-first scoring, and fake-gateway sanitized storage. It does not call OpenAI and does not claim optional live quality gate readiness.

For P23 optional OpenAI quality confidence evidence, run:

```bash
LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1 make test PYTEST_ARGS="tests/eval/test_p23_openai_quality_live_gate.py"
```

This live gate must not be part of the default required suite. If it is skipped, unavailable, or failed, P23 stays `production_ready: false`; treat the result as confidence evidence rather than a production blocker.
P26 live confidence uses the high-quality `openai_sp_semantic_analysis` profile by default; `openai_fast_test` remains a manual fast/test option.

For P24C fixture-first guide renderer/evaluator validation, run:

```bash
make test PYTEST_ARGS="tests/eval/test_p24_sp_migration_guide_quality.py tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py"
```

This renders and scores sanitized fixture expectations against existing artifact types. It does not require live PPM metadata, does not fall back to PLF, does not store SP source text or user guide text, and does not make P24 production-ready.

For P32 planner effectiveness and optional live confidence, run:

```bash
make test PYTEST_ARGS="tests/unit/agent_runtime/test_planner_effectiveness.py tests/eval/test_p32_live_confidence_planner_effectiveness.py"
P32_LIVE_CONFIDENCE_GATE=1 LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/eval/test_p32_live_confidence_planner_effectiveness.py"
```

The first command is fixture-first and does not call live OpenAI/PPM. The second command requires `OPENAI_API_KEY` and read-only `ppm` metadata access; success is confidence evidence only and does not change production readiness.

For P33 performance/scale fixture-first validation, run:

```bash
make test PYTEST_ARGS="tests/unit/api/test_metadata_tool_cache.py tests/unit/api/test_batch_sp_analysis.py tests/eval/test_p33_performance_scale.py tests/contract/test_openapi_and_env_sample_assets.py tests/unit/web/test_p14_product_ui_static.py"
```

This verifies process-local cache behavior, stable fact hashes, batch SP intake, planner cache metrics, and backpressure codes without live PPM or production readiness claims.

For P34 knowledge assetization fixture-first validation, run:

```bash
make test PYTEST_ARGS="tests/unit/api/test_knowledge_asset_service.py tests/eval/test_p34_knowledge_assetization.py tests/contract/test_openapi_and_env_sample_assets.py tests/unit/web/test_p14_product_ui_static.py"
```

This verifies sanitized versioned knowledge assets, fact graph/export, stable version reuse, manual v5 schema boundary, and no raw leakage. Knowledge assets are draft/reviewable organizational knowledge and do not imply production readiness.

P24 status interpretation:

- `PASSED`: the fixture-first renderer/evaluator meets every threshold, keeps `productionReady: false`, preserves `REVIEW_REQUIRED` for unsupported or low-evidence claims, and has no storage safety findings or PPM-to-PLF fallback.
- `HOLD`: the fixture-first gate passes, but optional live confidence evidence is skipped, unavailable, failed, or blocked by local prerequisites. This is confidence evidence only and must not become a production readiness claim.
- `FAILED`/blocker: any threshold miss, forbidden storage payload, PLF fallback for PPM, production-ready or automatic conversion claim, row-data access, procedure execution, business DB DDL/DML, automatic apply/deploy, or P25+ Java/MyBatis expansion described as P24 completion.

For P27 dependency evidence tooling validation, run:

```bash
make test PYTEST_ARGS="tests/unit/test_mcp_catalog.py tests/unit/mcp/test_tool_registry.py tests/contract/mcp/test_tool_invocation_contract.py tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py tests/unit/api/test_metadata_service.py tests/integration/api/test_api_workflow_routes.py"
```

For explicit P27 hard-live validation, run:

```bash
P27_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/eval/test_p27_dependency_evidence_hard_live_gate.py"
```

P27 status interpretation:

- `PASSED`: catalog, handler, contract, and API summary tests agree that the new dependency tools are active/read-only/structured-only, `get_procedure_dependencies` declares the resolution evidence fields, and standard MCP responses retain snapshot/evidence refs.
- `HOLD`: fixture-first tooling passes but explicit P27 hard-live evidence is skipped/unavailable or local PPM prerequisites are missing. This is expected outside approved live environments and does not imply production readiness.
- `FAILED`/blocker: P27 tools become inactive, writable, or handlerless, any contract accepts free-form SQL or row data, raw definition/provider/prompt storage is allowed, PPM falls back to PLF, uncertain dependencies are promoted as deterministic facts, or `P27_HARD_LIVE_GATE=1` skips missing prerequisites.

## P15 Ops Gate

- Quality metrics: evidence coverage, review-required ratio, validation pass rate, generation reproducibility, and draft artifact completeness.
- Latency budgets: separate product targets and current live gates for PPM readiness, metadata inventory smoke, and fixture workflow smoke.
- Observability: logs and audit traces must carry correlation id plus request/job/artifact/profile/snapshot/blocker context.
- Redaction: connection strings, credentials, cookies, raw definition text, and row data must not be logged or committed to fixtures.
- DB permission check: use read-only metadata tools against `ppm`/`PPM`; no row-data reads, procedure execution, DDL/DML, or PLF fallback.

## Drift Memo

- OpenAPI: P21 adds recent jobs and latest validation read routes. Requested output groups remain separate from persisted artifact types.
- Domain: P18A adds the minimal versioned `CanonicalAnalysisModel` contract in `packages/domain` and keeps missing snapshot/registry/evidence bindings as explicit analysis blockers.
- MCP catalog: P27 dependency closure/reference resolution tools are active read-only fixture-first hardened tools with structured arguments and safe API summary exposure only.
- Knowledge: P34 adds manual-apply v5 knowledge asset DDL, `CanonicalAnalysisModel.v2`, sanitized asset/fact/export APIs, and Web summaries without widening the public MCP invoke allowlist.
- Validation rules: P26 adds guide/conversion recall scoring for LLM semantic quality while existing evidence/review-required rules continue to drive e2e/eval expectations.
- Policy: P26 documents high-quality semantic analysis defaults, while forbidden automatic publish, automatic DDL, row-data access, raw prompt/SP/provider-response storage, and PLF fallback boundaries remain unchanged.
- Env/profile: default metadata profile is now consistently `master`; platform DB profile `plf` remains available. Live MSSQL uses `MSSQL_METADATA_TDS_VERSION=7.4` by default, with `7.0` available for local Chakra/legacy proxy paths that reject default `python-tds` negotiation.
- LLM eval: P23/P26 includes contract quality assets, synthetic fixtures, staged high-quality semantic scoring, and guide/conversion recall. Default tests stay fake-gateway-only and preserve no-raw-trace storage.
- Migration guide eval: P24C renders sanitized guide-quality fixtures into existing draft artifact types and scores the artifact pair with a reusable fixture-first evaluator.

## Follow-Up Backlog

1. Implement real read-only live metadata adapter queries behind the MCP boundary.
2. Broaden CanonicalAnalysisModel coverage beyond the minimal P18A fixture-first contract.
3. Add publish API only after future approval semantics are explicitly reintroduced and fully enforced.
4. Verify auth/RBAC live wiring against an approved IdP/JWKS endpoint and PLF role membership source before claiming production-grade enterprise Auth/RBAC.
5. Expand eval fixtures beyond the single happy path to dynamic SQL, temp tables, transaction/TRY-CATCH, DDL drafts, and failure paths.
6. Mature DDL draft renderer while keeping schema apply/manual review outside automation.
7. Keep future live pilot reruns evidence-based: if P17B validation, P17C approval/audit binding, or hard-live PPM verification cannot be reproduced, return the scoped candidate to `NO_GO`.
8. Keep `AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED` as deferred future hardening until live auth/RBAC wiring closes without mock headers, hardcoded actors, fixture tokens, or committed secrets.
9. Keep P21 no-mock portal evidence conditional on PLF/PPM prerequisites; do not claim full production readiness from a local controlled live gate.
10. Keep optional P23 live quality gate evidence separate from default fixture-first scoring.
11. Broaden P24 guide fixtures only after additional sanitized deterministic facts exist; keep current renderer/evaluator fixture-first and draft-only.
12. Use explicit P27 hard-live results to reduce residual `REVIEW_REQUIRED` dependency evidence where catalog metadata can uniquely confirm targets, without introducing persisted artifact type changes, DB schema changes, or PLF fallback.
13. Keep knowledge assets reviewable until multi-process/shared knowledge indexing, lifecycle policy, and human curation workflows are designed.
