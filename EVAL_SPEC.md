# EVAL_SPEC.md

## P36 Output Renewal Eval Contract

P36 validates the breaking output renewal:

- final artifact types: `SP_ANALYSIS_DOC`, `DEPENDENCY_REPORT`, `DTO_DRAFT`, `SERVICE_DRAFT`, `MAPPER_INTERFACE`, `MAPPER_XML`
- removed public outputs/artifacts: `DTO_MODEL_DRAFT`, `VO_DRAFT`, `MODEL_DRAFT`, `DDL_DRAFT`
- SP analysis document flow: overview, dependency inventory, DML impact matrix, call flow, complexity analysis, appendix
- dependency report role: evidence dossier with SP analysis, Java/MyBatis, bounded SQL statement evidence, caveats, next evidence
- Java/MyBatis draft mode: evidence-backed business logic reconstruction with `REVIEW_REQUIRED` uncertainty

Passing P36 tests must not imply production readiness, automatic conversion, DDL apply, row-data access, procedure execution, or generated-source deployment.

## P37 Metadata DTO Draft Preview Eval Contract

P37 validates metadata-analysis DTO previews without changing the artifact persistence contract:

- `generateDtoDrafts` defaults to false and only opts into response/UI preview generation.
- `generatedDrafts` contains `DTO_DRAFT` preview content backed by sanitized TABLE/VIEW metadata
  evidence refs.
- missing PK, nullable columns, uncertain type mapping, description gaps, VIEW semantics, and
  other incomplete metadata remain `REVIEW_REQUIRED`.
- previews must not include raw SQL/SP definitions, row data, secrets, automatic source apply,
  DDL/DML execution, publish, deploy, or workflow artifact persistence claims.

## P38 Metadata Design Chat Eval Contract

P38 validates durable metadata design chat runs:

- `POST /api/v1/metadata/design-runs`, `GET /api/v1/metadata/design-runs/{runId}`, and
  `GET /api/v1/metadata/design-conversations/{conversationId}` expose sanitized run submit/polling.
- v10 `METADATA_DESIGN_RUNS` is manual-apply only and stores sanitized request/result/error JSON.
- field names, descriptions, and table hints drive read-only metadata lookup and standardization.
- `createTableScriptPreview` is present, review-required, and non-executable.
- optional `DTO_DRAFT` preview is returned inside the design result and is not workflow artifact persistence.

## P40 Metadata Design Natural-Language Chat Eval Contract

P40 validates the natural-language and multi-turn layer on top of P38:

- OpenAPI exposes `conversationMode`, `interpretedIntent`, and `appliedChanges`.
- Korean and English natural-language messages produce sanitized field candidates and evidence-backed previews.
- `REFINE_CURRENT` applies add/remove/type-change instructions to the latest successful conversation baseline.
- Missing baseline or ambiguous refinement remains `REVIEW_REQUIRED` and does not silently start a new design.
- Web static and smoke tests verify chat transcript/input, no field row UI, and no apply/execute/deploy/publish controls.
- Generated table scripts remain `createTableScriptPreview`; `DDL_DRAFT` and other retired tokens remain forbidden.
- no raw prompt/provider response, row data, full SQL/SP definition, procedure execution output,
  automatic DDL apply, publish, deploy, or retired artifact type revival is allowed.

## P41 SP Operation Model Renewal Eval Contract

P41 validates the operation-model renewal path for complex SP code generation:

- `SpOperationModel.v0.1` exists as an internal planning contract separate from
  `CanonicalAnalysisModel.v2`.
- `fixtures/eval/sp_operation_model_p41_manage_bond_v1.yaml` models
  `PCO_GU_ManageBond_PRC` with `CRUDFlag` branches `R/A/C/U/D/VENDOR_U/ONLINE_U`.
- The fixture contains sanitized statement evidence, branch conditions, and at least
  nine DTO blueprints so the desired output cannot collapse into one DTO.
- `JavaMyBatisSpWrapperRenderer` single-DTO behavior is accepted only for legacy
  requests that do not include `operationModel`; the fixture keeps this visible as
  `SINGLE_DTO_COLLAPSE_REVIEW_REQUIRED`.
- When `operationModel.dtoBlueprints` is supplied, `JavaMyBatisSpWrapperRenderer`
  must render a multi-file `DTO_DRAFT` bundle and keep Service, Mapper interface,
  and Mapper XML as single draft files wired to branch/use-case DTOs.
- The SP workflow must create or reuse an `LLM_SP_OPERATION_PLANNER` AgentRun for
  `JAVA_MYBATIS_DRAFT`, inject the validated `operationModel` into
  `GenerationContext.request`, and persist one `DTO_DRAFT` artifact row per DTO file.
- Workflow fallback cases such as missing procedure definition, disabled LLM planning,
  or planner failure must emit `P41_OPERATION_MODEL_REVIEW_REQUIRED` and an explicit
  `OperationModelReviewRequired` DTO instead of silently producing the legacy single DTO.
- Public artifact types remain unchanged; `DTO_DRAFT` is the internal multi-file
  bundle carrier for operation-model generation and no new public artifact type is introduced.
- Cross-DB write, called procedure I/O, and uncertain TVF/procedure kind remain
  `REVIEW_REQUIRED`.
- raw SP definitions, raw prompts, raw provider responses, row data, secrets,
  procedure execution, business DB DDL/DML, source apply, and PLF fallback are forbidden.

통과 기준:
- `make test PYTEST_ARGS="tests/contract/test_p41_sp_operation_model_prompt_assets.py tests/eval/test_p41_sp_operation_model.py"` 통과
- `make test PYTEST_ARGS="tests/unit/api/test_workflow_service.py tests/integration/api/test_api_workflow_routes.py tests/unit/generation tests/eval/test_p36_output_renewal_quality.py tests/eval/test_p41_sp_operation_model.py tests/unit/agent_runtime/test_sp_operation_planner.py tests/unit/analysis/test_sp_statement_evidence_extractor.py tests/unit/agent_runtime/test_sp_operation_model_schema.py tests/contract/test_p41_sp_operation_model_prompt_assets.py"` 통과
- `production_ready: false` 유지
- 후속 P41B~P41F 순차 작업이 manifest 와 prompt pack 에 연결됨

## P42 AI Draft Pack Renewal Eval Contract

P42 validates the AI Draft Pack groundwork for complex SP Java/MyBatis drafts:

- `AiJavaMyBatisDraftPack.v0.1` exists as an internal draft-pack contract for file inventory,
  file content, evidence refs, review markers, and quality gates.
- `fixtures/eval/ai_draft_pack_p42_manage_bond_v1.yaml` models the expected
  `PCO_GU_ManageBond_PRC` draft pack without storing raw SP text, raw guide body, raw prompts,
  raw provider responses, row data, or secrets.
- Public artifact types remain unchanged: `DTO_DRAFT`, `SERVICE_DRAFT`, `MAPPER_INTERFACE`, and
  `MAPPER_XML`.
- The ManageBond benchmark fixture requires separate DTO files:
  `ManageBondSearchCriteria`, `ManageBondSearchRow`, `ApproveAdvanceBondCommand`,
  `ApproveDefectBondCommand`, `FinanceTransferCommand`, `CreateBondCommand`,
  `CreateRetentionBondBatchItem`, `UpdateBondCommand`, `DeleteBondCommand`,
  `VendorBondUpdateCommand`, and `OnlineBondUpdateCommand`.
- Production workflow must not use ManageBond-specific runtime constants. It must derive
  `expectedInventory` and quality gates from sanitized operation contracts, DTO blueprints,
  statement evidence, branch responsibilities, and review markers.
- Service, Mapper interface, and Mapper XML remain single files but must reference the required
  DTOs and expose branch/use-case methods.
- P42C deterministic validation is static only: it checks Java/XML text, DTO/method references,
  Mapper XML shape, forbidden payload markers, and required `REVIEW_REQUIRED` markers without
  executing Java, SQL, Mapper XML, stored procedures, or database access.
- P42D wires `JAVA_MYBATIS_DRAFT` to the AI Draft Pack path before Java/MyBatis artifact
  persistence. A successful pack must pass the P42B schema and P42C quality gate, then persist one
  `DTO_DRAFT` row per DTO file path and exactly one `SERVICE_DRAFT`, `MAPPER_INTERFACE`, and
  `MAPPER_XML` row.
- P42D artifact `extra` metadata must include `aiDraftPackSchema`, `aiDraftPackTargetRef`,
  `aiDraftPackAgentRunId`, `aiFileRole`, `operationIds`, `dtoRole` for DTOs, `qualityScore`,
  `bundleFilePath`, `aiEvidenceRefs`, and `reviewMarkers`.
- P42D failure behavior is explicit: gateway/schema/quality failures record
  `P42_AI_DRAFT_PACK_FAILED`, while disabled or unavailable safe planning context records
  `P42_AI_DRAFT_PACK_REVIEW_REQUIRED`. Neither case may persist Java/MyBatis fallback skeleton
  artifacts.
- P42E adds a local API workflow replay gate for `PCO_GU_ManageBond_PRC`. The replay uses fake
  metadata/model gateways and sanitized fixtures, treats `job_6864d2734e` as audit history only,
  and requires a new job to persist non-empty multi-DTO AI Draft Pack artifacts.
- P42E reconstructs the persisted Java/MyBatis artifacts into an
  `AiJavaMyBatisDraftPack.v0.1` payload and reruns the P42C quality validator so the route-level
  output satisfies the ManageBond fixture contract.
- P42F is the docs and quality-gate closure: docs must describe the implemented P42 path without
  claiming production readiness, and the final gate must run P42 targeted tests, P41 targeted
  tests, P36 generation regression, and `git diff --check`.
- P42G is an optional live confidence replay for the residual P42E risk. It is disabled by default
  with `P42_LIVE_REPLAY_GATE=0`. `P42_LIVE_REPLAY_MODE=sanitized_fixture` uses sanitized fixture
  facts and the existing OpenAI-compatible gateway without live PPM metadata or raw SP external
  export; `P42_LIVE_REPLAY_MODE=live_ppm` uses live read-only `ppm` metadata and remains gated by
  raw-SP-to-remote-model approval.
- P42G must fail before live access when required env is missing, must not run the stored procedure
  or query row data, must not write generated source or platform DB rows, and must scan persisted
  in-memory artifacts/agent traces for raw SP, raw prompt, raw provider response, row-data, and
  secret leakage.
- After P42H, P42G must not use ManageBond fixture inventory as a runtime fallback. If live
  metadata cannot produce branch-level operation evidence and the operation model remains
  `P41_OPERATION_MODEL_REVIEW_REQUIRED`, the live gate should fail with sanitized review-required
  diagnostics instead of passing through hardcoded DTO inventory.
- P42G passing means confidence evidence only. It does not make P42 production-ready and does not
  approve automatic conversion, publish, deploy, DDL/DML apply, or generated-source apply.
- P42H adds a generic inventory-contract gate: collapsed complex-SP inventories, uncovered
  statement evidence, missing DTO blueprint coverage, and write/call operations without command,
  batch item, or call request DTOs must fail as `P42_INVENTORY_CONTRACT_INCOMPLETE` before
  Java/MyBatis artifacts are persisted.
- `OperationModelReviewRequired*`, generic single-DTO collapse, fixture-specific
  `ManageBondDTO`, blank content, missing DTO references, source apply/deploy claims, and raw
  SP/guide storage are blockers.
- Cross-DB write, called procedure I/O, uncertain TVF/procedure kind, result-shape variants, and
  transaction boundary gaps remain `REVIEW_REQUIRED`.
- P42A is groundwork only. P42B-F implement schema/gateway, deterministic validator, workflow
  wiring, replay gate, and docs quality gate.
- P42 does not authorize UI changes, public API expansion, DB schema changes, public MCP route
  expansion, row-data access, procedure execution, business DB DDL/DML, automatic DDL apply,
  generated-source deployment, or production readiness.

Passing criteria:
- `make test PYTEST_ARGS="tests/contract/test_p42_ai_draft_pack_prompt_assets.py tests/eval/test_p42_manage_bond_ai_draft_quality.py"` passes.
- P42D workflow gate includes
  `make test PYTEST_ARGS="tests/unit/api/test_workflow_service.py tests/unit/agent_runtime/test_ai_draft_pack_planner.py tests/unit/agent_runtime/test_ai_draft_pack_schema.py tests/unit/validation/test_ai_draft_pack_validator.py tests/eval/test_p42_manage_bond_ai_draft_quality.py"`.
- P42E replay gate includes
  `make test PYTEST_ARGS="tests/integration/api/test_api_workflow_routes.py tests/unit/api/test_workflow_service.py tests/eval/test_p42_manage_bond_ai_draft_quality.py tests/unit/validation/test_ai_draft_pack_validator.py tests/eval/test_p36_output_renewal_quality.py tests/eval/test_p41_sp_operation_model.py"`.
- P42F final gate includes
  `make test PYTEST_ARGS="tests/contract/test_p42_ai_draft_pack_prompt_assets.py tests/eval/test_p42_manage_bond_ai_draft_quality.py tests/unit/agent_runtime/test_ai_draft_pack_schema.py tests/unit/agent_runtime/test_ai_draft_pack_planner.py tests/unit/validation/test_ai_draft_pack_validator.py tests/unit/api/test_workflow_service.py tests/integration/api/test_api_workflow_routes.py tests/contract/test_p41_sp_operation_model_prompt_assets.py tests/eval/test_p41_sp_operation_model.py tests/unit/agent_runtime/test_sp_operation_model_schema.py tests/unit/agent_runtime/test_sp_operation_planner.py tests/unit/analysis/test_sp_statement_evidence_extractor.py tests/unit/generation tests/eval/test_p36_output_renewal_quality.py"`.
- P42G disabled/default gate includes
  `make test PYTEST_ARGS="tests/eval/test_p42_live_ai_draft_pack_replay_gate.py"`.
- Optional live P42G gate includes
  `P42_LIVE_REPLAY_GATE=1 P42_LIVE_REPLAY_MODE=sanitized_fixture LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 make test PYTEST_ARGS="tests/eval/test_p42_live_ai_draft_pack_replay_gate.py"`.
- Optional live P42G `live_ppm` confidence evidence includes
  `P42_LIVE_REPLAY_GATE=1 P42_LIVE_REPLAY_MODE=live_ppm LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1 MSSQL_ENABLE_LIVE_METADATA=1 MSSQL_METADATA_CONNECT_TIMEOUT_SECONDS=20 make test PYTEST_ARGS="tests/eval/test_p42_live_ai_draft_pack_replay_gate.py"`.

## P43 Framework Adoption Readiness Eval Contract

P43 evaluates whether introducing a framework improves complex SP analysis and
AI Draft Pack generation quality. P43A is groundwork only:

- `spec/eval/p43_framework_adoption_contract.yaml` exists and keeps
  `production_ready: false`.
- `fixtures/eval/framework_adoption_p43_manage_bond_v1.yaml` treats
  `PCO_GU_ManageBond_PRC` as a complex-SP benchmark, not a production-runtime
  special case.
- Candidate comparison keeps the current Responses/httpx gateway as baseline and
  evaluates OpenAI Agents SDK and LangGraph only behind an internal adapter.
- P43 must not install a new framework dependency in P43A.
- P43 must not change UI, public API, DB schema, public MCP routes, or public
  artifact types.
- Framework traces and tool calls must not store raw prompts, raw provider
  responses, raw SP definitions, raw guide body, row data, secrets, or failed
  generated Java/XML content.
- P43D adds explicit framework tool-context and trace-summary gates:
  `P43_FRAMEWORK_TOOL_CONTEXT_BLOCKED` blocks unsafe candidate context before a
  stage runs, and `P43_FRAMEWORK_RAW_TRACE_BLOCKED` blocks unsafe framework
  events or summaries before storage.
- Stored framework trace summaries are limited to adapter ids, candidate
  framework, stage/status, component ids, counts, hashes, blocker/failure codes,
  and numeric policy-safe metrics.
- OpenAI Agents SDK tracing and LangGraph persistence/checkpointers remain
  adoption blockers until sensitive input/output capture and graph-state
  persistence are proven redacted.
- P43E replay is retained as historical evidence only. P49 removes the broad
  replay gate from active eval collection and moves any needed fake/baseline
  adapter behavior to test helpers.
- Historical P43 evidence includes a synthetic complex-SP collapse guard so
  candidate success cannot depend on ManageBond-specific DTO names or a
  production-runtime answer key.
- P43F records the decision as `pilot`, with `docs/framework-adoption-decision-p43.md`
  as the evidence-backed decision report. P49 supersedes the
  production-exported baseline adapter scaffold; the current Responses/httpx
  gateway remains retained for P-GPT default compatibility and emergency
  rollback.
- The final decision must be `adopt`, `pilot`, or `defer`, and each outcome keeps
  `production_ready: false` until a separate production readiness gate exists.
- ManageBond is a benchmark fixture for detecting generic failures such as
  complex-SP two-DTO collapse, missing branch/use-case coverage, raw trace
  leakage, and fallback skeleton persistence. It is not a hardcoded answer key.

Passing criteria:
- `make test PYTEST_ARGS="tests/contract/test_p43_framework_adoption_prompt_assets.py"` passes.
- P49 active framework gates include `@framework-contracts` and
  `@framework-runtime`; the removed P43 replay file is not an active gate.
- `git diff --check` passes.

## P44 Framework Runtime Adoption Eval Contract

P44 supersedes P43 as the active framework direction. It adopts OpenAI Agents SDK
for OpenAI remote `AiJavaMyBatisDraftPack.v0.1` generation and LangGraph for the
AI Draft Pack stage graph while keeping generated artifacts `production_ready:
false` / `productionReady=false`.

Acceptance checks:
- `spec/eval/p44_framework_runtime_adoption_contract.yaml` declares
  `framework_adoption_decision: adopt`, `primary_generation_runtime:
  openai_agents_sdk`, `orchestration_runtime: langgraph`, and
  `generated_artifacts_production_ready: false`.
- P43 remains historical evidence with `superseded_by:
  p44_framework_runtime_adoption@0.1.0`; it is not rewritten as if P43 had
  adopted a real framework.
- Dependency/import tests prove `openai-agents==0.17.2` and `langgraph==1.2.0`
  are available in the Python 3.14 test image.
- OpenAI Agents SDK adapter tests prove tracing is disabled, sensitive-data
  capture is excluded, schema failures are sanitized, and storage summaries keep
  only hashes/counts/stage names/model ids/token counts/failure codes.
- LangGraph tests prove stage order, repair routing, no persistent checkpointer,
  and sanitized transient graph state.
- Fixture replay tests run ManageBond and a synthetic complex SP through mocked
  OpenAI Agents SDK output plus actual LangGraph orchestration. ManageBond remains
  a benchmark only, not a production-runtime answer key.
- Two-DTO collapse, missing operation coverage, missing `REVIEW_REQUIRED`,
  unsafe trace, invalid schema, source apply, deploy, procedure execution, and
  row data access remain blockers.

Passing criteria:
- `make test PYTEST_ARGS="tests/contract/test_p44_framework_runtime_adoption_assets.py tests/unit/agent_runtime/test_openai_agents_framework_adapter.py tests/unit/agent_runtime/test_langgraph_ai_draft_pack_orchestrator.py tests/unit/api/test_workflow_service.py tests/eval/test_p44_framework_runtime_replay.py tests/eval/test_p42_manage_bond_ai_draft_quality.py tests/eval/test_p41_sp_operation_model.py tests/eval/test_p36_output_renewal_quality.py"` passes.
- `git diff --check` passes.

P45/P46 continuation:
- P45 adds `tests/eval/test_p45_openai_agents_live_gate.py` as an optional
  evidence gate. It runs only with `P44_OPENAI_AGENTS_LIVE_GATE=1`,
  `LLM_ENABLE_REMOTE=1`, `LLM_REMOTE_PROVIDER=openai` or `pgpt`,
  `OPENAI_API_KEY`, and OpenAI Agents trace redaction env locks. Official
  evidence uses `OPENAI_BASE_URL` empty or `https://api.openai.com/v1`.
  Approved P-GPT-compatible evidence additionally requires explicit
  `AI_GENERATION_RUNTIME=openai_agents` and `OPENAI_BASE_URL` or
  `OPENAI_RESPONSES_URL`; unknown custom endpoints remain blocked until
  classified. The default suite skips it without OpenAI, PPM, PLF, row data, or
  procedure execution.
- P46 adds `spec/eval/p46_rollback_removal_decision.yaml`. The decision is
  `retain_limited_rollback_not_active_default`: OpenAI defaults to OpenAI Agents
  SDK plus LangGraph, while `responses_httpx` remains only for P-GPT default
  compatibility and emergency rollback. Deletion is not approved.
- `make test PYTEST_ARGS="tests/contract/test_p45_p46_framework_runtime_gates.py tests/eval/test_p45_openai_agents_live_gate.py"` validates the disabled/default gate and contract assets without live calls.

## P47 Generic AI Draft Quality Uplift Eval Contract

P47 keeps P44-P46 real framework adoption active and improves complex-SP draft
quality without ManageBond-specific hardcoding.

Acceptance checks:
- `spec/eval/p47_generic_ai_draft_quality_uplift_contract.yaml` exists and keeps
  generated artifacts `production_ready: false`.
- `prompt:ai_java_mybatis_draft_pack@0.2.0` renders
  `DraftPackEvidenceBundle.v0.1` plus operation coverage, DTO responsibility,
  review marker, and mapper coverage matrices.
- The OpenAI live profile for AI Draft Pack generation is `openai_ai_draft_pack`.
  `OPENAI_MODEL_AI_DRAFT_PACK` falls back to `OPENAI_MODEL_ANALYSIS`, and the
  default live quality path must not use `openai_fast_test`.
- ManageBond DTO/method names are benchmark comparison metrics only. Generic
  pass/fail gates are based on discovered operation coverage, DTO separation,
  mapper wiring, schema validation, and required `REVIEW_REQUIRED` markers.
- The P42 live probe reports ManageBond benchmark metrics separately from generic
  validator pass/fail and stores no raw SP, prompt, provider response, row data,
  secrets, failed Java/XML payloads, source apply, or deploy claims.
- P42 sanitized fixture live replay and live_ppm replay both route through the
  same schema and P42C deterministic validator. The planner's DTO reference guard
  applies generically to all successful draft-pack outputs, not only repair
  retries, so non-DTO Service/Mapper/XML files preserve deterministic DTO
  responsibility references without ManageBond-specific hardcoding.

Passing criteria:
- `make test PYTEST_ARGS="tests/contract/test_p47_generic_ai_draft_quality_uplift_assets.py tests/unit/agent_runtime/test_ai_draft_pack_planner.py tests/eval/test_p42_live_ai_draft_pack_replay_gate.py"` passes.
- P36/P41/P42/P44/P45/P46 regression gates continue to pass.
- Optional live failures are reported with sanitized stage/blocker diagnostics
  only and do not imply production readiness.

## P48 Unified Structured Framework Runtime Eval Contract

P48 extends the adopted P44 framework runtime to every internal structured LLM
path without expanding public product surfaces.

Acceptance checks:
- `spec/eval/p48_unified_framework_runtime_contract.yaml` exists and declares
  `AiStructuredFrameworkAdapter.v0.1`, `FrameworkModelGateway`, and
  `OpenAIAgentsStructuredAdapter`.
- The runtime matrix covers `invoke_semantic_analysis`, `plan_metadata_tools`,
  `analyze_metadata`, `plan_platform_tools`, `plan_sp_operation_model`, and the
  existing AI Draft Pack path.
- Remote structured calls default to `openai_agents` for both official OpenAI
  and P-GPT-compatible endpoints; `AI_STRUCTURED_LLM_RUNTIME=responses_httpx`
  remains the explicit emergency rollback path.
- Unit tests prove the structured adapter validates semantic analysis, metadata
  tool planning, metadata analysis, platform tool planning, and SP operation
  model outputs through existing strict parsers and sanitized trace summaries.
- Regression tests prove metadata analyze, durable analysis runs, metadata
  design chat, SP workflow semantic analysis, SP operation planning, platform
  planners, MCP tool planners, and P44 AI Draft Pack replay still pass.
- The metadata design planner prompt metadata includes `toolNames`, matching the
  bounded allowed tool list used in the payload.
- P48 stores no raw prompts, raw provider responses, raw SP definitions, raw
  guide bodies, row data, secrets, or failed Java/XML payloads.
- P48 adds no public API, DB schema, UI, public MCP route, public artifact type,
  source apply, deploy, row-data query, procedure execution, automatic
  conversion approval, or production readiness claim.

Passing criteria:
- `make test PYTEST_ARGS="tests/contract/test_p48_unified_framework_runtime_assets.py tests/unit/agent_runtime/test_openai_agents_structured_adapter.py tests/unit/agent_runtime/test_semantic_runtime.py tests/unit/agent_runtime/test_sp_operation_planner.py tests/unit/api/test_metadata_analysis_service.py tests/unit/api/test_metadata_design_service.py tests/unit/api/test_ai_tool_orchestrator.py tests/unit/api/test_platform_tool_orchestrator.py tests/unit/api/test_workflow_service.py tests/eval/test_p30_metadata_ai_mcp_analysis.py tests/eval/test_p31_metadata_object_insight_depth.py tests/eval/test_p38_metadata_design_chat.py tests/eval/test_p40_metadata_design_natural_language_chat.py tests/eval/test_p44_framework_runtime_replay.py"` passes.
- `git diff --check` passes.

## P49 Framework Runtime Cleanup Eval Contract

P49 consolidates framework-runtime evidence and gates after the P48 migration.
`spec/eval/p49_framework_runtime_consolidation_cleanup.yaml` is the cleanup
index. P48 is the active structured runtime matrix, P44 is the active AI Draft
Pack OpenAI Agents plus LangGraph runtime, and P43 is historical evidence only.

Acceptance checks:
- P49 declares retained rollback semantics: `responses_httpx` stays for P-GPT
  AI Draft Pack compatibility and explicit emergency rollback, but not as the
  default structured LLM runtime.
- Production runtime exports no longer include P43 baseline/fake framework
  adapter symbols; test-only equivalents live under `tests.helpers`.
- Broad P43 replay gates are replaced by a small historical asset contract check
  that verifies P43 is superseded and policy-safe.
- Suite aliases `@framework-contracts` and `@framework-runtime` select the active
  framework contract/runtime gates without collecting the removed P43 replay.
- P49 adds no public API, DB schema, UI, public MCP route, public artifact type,
  source apply, deploy, row-data query, procedure execution, automatic
  conversion approval, or production readiness claim.

Passing criteria:
- `make test PYTEST_ARGS="@framework-runtime"` passes.
- `make test PYTEST_ARGS="tests/unit/agent_runtime tests/unit/api/test_workflow_service.py tests/contract"` passes.
- `make test-quality` passes.
- Approved live-confidence fixture-first gates pass before any full
  `@live-confidence -- -vv -s -x` run.
- `git diff --check` passes.

## P35 Source Context Eval Gate

Required checks for Copilot-style SP analysis:

- Source map unit coverage proves `ProcedureSourceMap` extracts signature, parameter, DML,
  result-set, call, temp-table, transaction/TRY-CATCH, and dynamic SQL spans without storing raw
  SQL text in serialized payloads.
- Semantic prompt coverage proves full `procedureDefinition` text is replaced by stage-specific
  `ContextPack` retrieved spans, and persisted trace summaries expose only sanitized
  `analysisCoverage` and `sourceContextSummary`.
- Context overflow coverage proves provider `context_length_exceeded` failures retry with reduced
  spans and add `LLM_CONTEXT_BUDGET_REVIEW_REQUIRED`; evidence-digest fallback remains
  `REVIEW_REQUIRED`.
- Integration coverage for long SP fixtures must finish at `VALIDATION_COMPLETE` without raw SP
  definitions in metadata, artifacts, knowledge assets, exports, or trace summaries.
- Multi-SP dependency coverage proves confirmed same-profile and same-server cross-database
  dependency procedures are stored as child `LLM_SEMANTIC_ANALYST_DEPENDENCY` AgentRuns, only
  sanitized guidance is reduced into the root run, and dynamic/unresolved/unsafe cross-db/
  cross-server/caller-dependent items remain `REVIEW_REQUIRED`.

## 목적

이 문서는 저장소에서 "완료"를 판단하는 평가 규격을 정의한다.  
핵심 원칙은 **기능 통과만으로 충분하지 않다**는 점이다.  
정확성, 근거, 정책 준수, 재현 가능성, 문서 정합성까지 함께 본다.

## 평가 원칙

- 단위 테스트보다 계약/행동 검증을 우선하는 영역을 분리한다.
- 생성 계열 기능은 fixture 와 rubric 으로 평가한다.
- 동일 입력 + 동일 snapshot + 동일 registry version 조합이면 결과가 재현 가능해야 한다.
- 품질 게이트는 자동 검증 + 수동 리뷰 포인트 둘 다 남긴다.

## 평가 축

| 축 | 질문 |
|---|---|
| Contract correctness | API/MCP/DDL/Canonical 모델이 계약대로 동작하는가 |
| Analysis quality | SP 구조, 의존성, 패턴 식별이 정확한가 |
| Generation quality | 문서/코드/DDL 초안 형식과 필수 정보가 올바른가 |
| Evidence coverage | 결과가 근거를 갖거나 검토 필요로 표기되는가 |
| Policy compliance | 금지 행위를 하지 않았는가 |
| Reproducibility | 동일 조건에서 결과가 안정적으로 재현되는가 |
| Docs sync | 코드/계약/문서가 어긋나지 않는가 |

## 필수 평가 스위트

### 1. Metadata MCP Contract
대상:
- tool input schema
- tool output schema
- error model
- read-only enforcement

필수 체크:
- 자유 SQL 입력 불가
- snapshot/evidence 필드 존재
- 오류 코드가 문서화된 형태와 일치
- 실제 데이터 접근 도구 없음

통과 기준:
- 필수 contract test 100% 통과

### 2. Analysis Model Accuracy
대상:
- procedure parameters
- call graph
- read/write dependencies
- transaction / exception / dynamic SQL / temp table flags

필수 체크:
- 대표 fixture 에 대해 required fields 누락 없음
- 분석 결과가 canonical schema 에 적합
- 불확실한 추론은 review_required 로 표시

통과 기준:
- required field presence 100%
- 대표 fixture 기준 핵심 필드 exact match 또는 허용된 불확실성 표기

### 3. Generation Format Conformance
대상:
- SP analysis doc
- dependency report
- Mapper XML / Interface / Service
- DTO draft
- bounded SQL evidence dossier (no executable DDL draft output)

필수 체크:
- artifact type 별 필수 섹션 존재
- naming/package 규칙 충족
- generator version / evidence refs 존재

통과 기준:
- required section presence 100%
- naming/package rule violations 0

### 4. Draft Validation Workflow
대상:
- validation reports
- preview
- draft-quality caveats
- publish/apply absence

필수 체크:
- validation 없이 publish 불가
- 기본 workflow 는 approval decision 없이 `VALIDATION_COMPLETE` 에서 멈춤
- approval/review route, review write, reviewer identity write 없음
- validation 결과는 `qualityCaveats` 로 근거 caveat 를 노출

통과 기준:
- 상태 전이 규칙 위반 0

### 5. Policy & Security
대상:
- forbidden action checks
- secrets handling
- unsafe command use
- doc drift
- production auth/RBAC source and enforcement evidence

필수 체크:
- 실제 데이터 접근 코드 없음
- 자동 DDL 실행 경로 없음
- 민감 환경값 log/fixture 유출 없음
- 정책 문서와 구현이 모순되지 않음
- production identity source 가 verified OIDC/JWT 로 문서화되어 있고 role source 가 PLF auth table 로 연결됨
- validation enforcement 구현 시 unauthorized negative test 가 존재함
- live IdP/JWKS 와 PLF role membership 검증이 없으면 production-grade enterprise Auth/RBAC claim 을 금지하고 deferred future hardening 으로 유지함

통과 기준:
- P0 위반 0
- auth/RBAC source 문서화가 없거나 mock header/hardcoded actor 로 production 을 가장하면 blocker

### 6. Reproducibility
대상:
- same input / same snapshot / same registry versions

필수 체크:
- hash 또는 stable normalized output 비교
- generator version and registry refs persisted

통과 기준:
- 결정론적 결과가 필요한 artifact 는 동일 결과
- 비결정론 허용 artifact 는 차이 범위가 문서화됨

### 7. Integration Happy Path
대상:
- request submission
- job status
- draft artifact preview
- validation report
- validation-complete terminal draft status

필수 체크:
- 기본 경로는 `master` metadata profile 과 fixture-backed MCP snapshot 을 사용
- job 은 `VALIDATION_COMPLETE`, current step 은 `VALIDATE`
- persisted artifact type 이 OpenAPI requested output group 과 구분됨
- validation `REVIEW_REQUIRED` 는 user review flow 가 아니라 evidence caveat 로 유지됨
- approval decision API 는 제품/API surface 에 없음

통과 기준:
- `make test PYTEST_ARGS="tests/e2e tests/eval"` 통과
- `PUBLISHED` 상태, 자동 DDL, row-data access 흐름 0건

### 8. P21 No-Mock Portal Gate
대상:
- Python 3.14 host/Docker baseline
- Web HTTP-only runtime path
- PLF workflow repository
- PPM read-only metadata access

필수 체크:
- `requirements/lock/py314-dev.txt`, `python:3.14-slim`, `requires-python >=3.14`, Ruff `py314` target 이 현재 기준임
- Web functional pages 는 mock adapter 나 demo ids 에 의존하지 않음
- `/artifacts/[artifactId]` page-load 는 validation write 를 만들지 않고 latest validation GET 만 수행함
- `/review/decision` 화면과 approval CTA 는 기본 Web UI 에서 제거되며 직접 접근은 404 로 처리됨
- `P21_LIVE_PORTAL_GATE=1` 에서 PLF/PPM env 가 없으면 skip 이 아니라 blocker failure 로 보고함

통과 기준:
- `make test PYTEST_ARGS="tests/contract/test_p21_no_mock_prompt_assets.py tests/eval/test_p21_live_portal_no_mock_gate.py"` 통과
- `make test-web-smoke` 통과
- live gate 성공 전에는 `production_ready: false` 유지

### 9. P22 OpenAI LLM Agent Runtime Gate
대상:
- `packages/agent-runtime` model gateway / prompt renderer / structured parser
- `SPAnalysisOptions` typed LLM options
- `GET /api/v1/jobs/{jobId}/agent-runs`
- no-raw-trace platform storage and web trace summary

필수 체크:
- 기본 테스트는 `FakeModelGateway` 를 사용하고 외부 OpenAI API 를 호출하지 않음
- semantic analysis profile 기본값은 `gpt-5.5` 이며 `OPENAI_MODEL_ANALYSIS` 로 live confidence 모델을 바꿀 수 있음. fast/test profile 은 수동 평가 선택지로 남고 기본값은 `gpt-5-nano` 다.
- remote 실행은 `LLM_ENABLE_REMOTE=1`, `LLM_ALLOW_SP_TEXT=1`, `OPENAI_API_KEY` gate 를 요구
- raw prompt, raw SP definition, raw OpenAI response text 는 DB/API/artifact/test output 에 저장하지 않음
- `useAiToolOrchestration=true` 가 기본값이며 `useLlmAnalysis=false` 이면 자동 비활성화됨
- metadata tool planning 은 strict `schema:mssql_metadata_tool_plan@0.1.0` 출력만 허용하고,
  실제 MCP 실행은 workflow deterministic policy gate 와 내부 registry 로만 수행함
- `usePlatformToolOrchestration=true` 가 기본값이며 `useLlmAnalysis=false` 이면 자동 비활성화됨
- platform tool planning 은 strict `schema:platform_tool_plan@0.1.0` 출력만 허용하고,
  실제 실행은 current job/db profile/target scope gate 와 내부 platform registry 로만 수행함
- platform tool 결과는 sanitized `platformToolEvidence` 와 `platform.<toolName>.<hash>` fact 로만
  semantic prompt 에 전달되며 public invoke API, artifact full content, row data, DDL/DML,
  approval/review write, export creation 을 만들지 않음
- structured output 은 `schema:llm_semantic_analysis@0.4.1` strict JSON schema 를 통과해야 하며 guide/conversion 품질 필드와 한국어 작업자-facing 자유 텍스트를 포함해야 함
- 언어 경계는 한국어 자유 텍스트와 영어 machine contract 의 공존으로 검증한다. JSON key,
  enum/status/code, artifact type, rule id, section id, evidence ref, SQL/Java 식별자는
  번역하지 않는다.
- P-GPT 등 remote provider drift 는 strict validation 을 먼저 시도한 뒤, schema/OpenAPI 를 넓히지 않고 extra field/alias/status/severity 만 결정론적으로 정규화한다. 저장되는 normalizer metadata 는 path/code 수준이며 raw provider response, prompt, SQL/SP text 는 저장하지 않는다.
- LLM inference evidence 는 validation 에서 `REVIEW_REQUIRED` 로 유지됨

통과 기준:
- `make test PYTEST_ARGS="tests/unit/agent_runtime tests/unit/api/test_workflow_service.py tests/integration/api/test_api_workflow_routes.py tests/contract/test_p22_agent_runtime_assets.py tests/eval/test_p22_openai_live_agent_gate.py"` 통과
- `make test-web-smoke` 또는 HTTP adapter smoke 에서 LLM trace summary 표시 확인
- 선택 live gate 는 아래 명령으로 별도 수행하며, 기본 게이트에 포함하지 않음

```bash
LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1 make test PYTEST_ARGS="tests/eval/test_p22_openai_live_agent_gate.py"
```

### 10. P23 LLM SP Analysis Quality Eval Contract
대상:
- `spec/eval/p23_llm_sp_analysis_quality_contract.yaml`
- `fixtures/eval/llm_sp_analysis_quality_p23_v1.yaml`
- `tests/eval/test_p23_llm_sp_analysis_quality.py`
- `ops/codex-parallel/prompts/23*.md`
- P23A~P23D split execution manifest

필수 체크:
- P23 은 P22 runtime 이후의 평가 확장으로 분리한다
- P23A 는 계약/프롬프트 자산을 만들고, P23B 는 synthetic simple/medium/complex fixture 와 fake-gateway 검증을 추가한다
- P23C 는 P23B fixture 를 `FakeModelGateway` 로 반복 실행하고 quality score 를 계산한다
- P-GPT live confidence 경로는 prompt quality hints 와 deterministic safety net 을 사용해 read-only lookup, transaction/DML, dynamic SQL/cross-DB, uncertain result-shape coverage 를 보강한다. Safety net claims 는 `DETERMINISTIC_SAFETY_NET_*` prefix 와 allowed deterministic fact id 만 사용하며 draft/reviewable confidence evidence 로만 취급한다.
- simple/medium/complex stored procedure scenario matrix 와 authored fixture 를 유지한다
- P26 live confidence 는 기본적으로 `openai_sp_semantic_analysis` / `OPENAI_MODEL_ANALYSIS` 를 사용한다. fast/test profile 은 수동 평가 선택지로 남고 기본값은 `gpt-5-nano` 이며 `OPENAI_MODEL_FAST_TEST` 로 바꿀 수 있다.
- LLM 보강 필드는 `business_rules`, `modernization_points`, `risk_flags`, `review_markers`, `conversion_guidance`, `migration_guide_insights`, `assumptions` 로 제한한다
- runtime 은 SP별 `SemanticAnalysisTask` 로 fan-out 가능하며 `LLM_SP_CONCURRENCY=2` 를 기본 병렬도 한계로 둔다
- live structured schema 는 deterministic fact id 를 `evidenceRefs` enum 으로 제한하고, runtime 은 invalid/trace evidence refs 를 deterministic fact id 로 repair 한다
- dynamic SQL, unsafe cross-DB, unsupported dependency/table/function/procedure claim 의 필수 `REVIEW_REQUIRED` marker 는 deterministic guard 가 보강한다
- `LLM_INFERENCE` evidence 와 unsupported dependency/table/function claim 의 `REVIEW_REQUIRED` 처리 기준을 둔다
- scoring runner 는 semantic recall, evidence discipline, overclaim control, storage safety 를 검증하며 raw prompt/SP/provider response text 를 저장하지 않는다
- storage safety 는 adversarial raw SQL/provider-trace echo payload 를 실패로 판정하며, runtime 은 저장 전 sanitizer 와 `LLM_OUTPUT_STORAGE_SANITIZED` review marker 로 이를 차단한다
- bounded AI tool orchestration 결과는 sanitized `aiToolEvidence` 와 `mcp.<toolName>.<hash>` deterministic fact id 로만 semantic prompt 에 전달한다
- bounded platform tool orchestration 결과는 sanitized `platformToolEvidence` 와
  `platform.<toolName>.<hash>` deterministic fact id 로만 semantic prompt 에 전달한다
- raw prompt, raw SP definition, raw OpenAI response text, row data, secret 은 fixture trace/API/Web 산출물에 저장하지 않는다
- optional live gate 는 confidence signal 이며 기본 계약 검증이나 production readiness 의 필수 조건이 아니다

판정 해석:
- 통과: 기본 fixture-first P23 테스트가 통과하고 `semantic_recall >= 0.75`, `guide_conversion_recall >= 0.8`, `evidence_discipline >= 0.9`, `unreviewed_overclaims <= 0`, `storage_safety_findings <= 0` 을 만족한다.
- 보류: fixture-first gate 는 통과했지만 optional live confidence gate 가 skip/fail/unavailable 이거나 로컬 검증 prerequisites 가 준비되지 않았다. 이 경우 P23 confidence signal 만 부족한 상태이며 production readiness 로 해석하지 않는다.
- 실패/blocker: quality threshold 미달, raw prompt/SP/provider response 저장, `production_ready: true` 주장, PPM-to-PLF fallback, model/profile/prompt/schema drift, 또는 P24 document/code generation 범위를 P23 완료로 표현하는 경우다.

통과 기준:
- `make test PYTEST_ARGS="tests/eval/test_p23_llm_sp_analysis_quality.py tests/unit/agent_runtime tests/contract/test_p23_llm_eval_contract_prompt_assets.py"` 통과
- P23A -> P23B -> P23C -> P23D 병합 순서가 manifest 에 명시됨
- optional live quality gate 는 아래 명령으로 별도 수행하며, 실패해도 production blocker 로 과장하지 않음
- P23D 완료 후에도 별도 production readiness gate 전까지 `production_ready: false` 유지

```bash
LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1 make test PYTEST_ARGS="tests/eval/test_p23_openai_quality_live_gate.py"
```

### 11. P24 SP Migration Guide Quality Eval Contract

P24C/P24 v0.3 implementation status: fixture-first renderer/evaluator coverage is now
implemented for the existing `SP_ANALYSIS_DOC` and `DEPENDENCY_REPORT` artifact
types. The renderer uses Korean user-facing headings with stable hidden section
anchors and guide-style overview, feature/branch, dependency, DML, and critical
phase tables. The evaluator scores the rendered artifact pair with no new persisted
artifact type, no API/schema changes, no live DB access, no raw prompt/SP/provider
response storage, and `production_ready: false`.

대상:
- `spec/eval/p24_sp_migration_guide_quality_contract.yaml`
- `fixtures/eval/sp_migration_guide_quality_p24_v1.yaml`
- `tests/eval/test_p24_sp_migration_guide_quality.py`
- `tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py`

필수 체크:
- P24A 는 contract/prompt/task/manifest 자산을 고정하고, P24B 는 sanitized fixture-first guide quality expectation 을 추가하며, P24C 는 기존 artifact type renderer/evaluator 로 fixture 를 점수화한다
- simple/medium/complex synthetic scenarios 가 required section taxonomy, internal `Confirmed`/`Needs verification` status 를 유지한 dependency inventory, table-level DML matrix, branch call flow, critical phase/risk metrics, appendix mappings, manual metadata extraction appendix, evidence refs 를 포함한다. 렌더링된 작업자-facing 표제와 설명은 한국어로 표시한다.
- manual metadata extraction appendix 는 SSMS 수동 실행용 metadata-only query/result paste template 만 포함하며 row data 조회, procedure execution, DDL/DML, raw definition output 을 금지한다
- P24C 는 기존 `SP_ANALYSIS_DOC` 와 `DEPENDENCY_REPORT` 를 재사용하고 새 persisted artifact type, API/Web/DB schema 변경, live DB access 를 만들지 않는다
- P24 v0.3 출력은 `## sp_overview` 같은 내부 section id 를 사용자-facing heading 으로 노출하지 않고, `<!-- section:{section_id} -->` 안정 anchor 와 한국어 heading/표 기반 문서를 사용한다
- fast/test profile 기본값은 `gpt-5-nano` 이며 optional live confidence 에서는 `OPENAI_MODEL_FAST_TEST` 로 모델을 바꿀 수 있다
- fixture 와 expected report 는 raw prompt, raw SP definition, raw OpenAI response text, row data, secret, 사용자 제공 guide 본문, 실제 운영 SP 원문을 저장하지 않는다
- unsupported dependency/table/function/unsafe cross-DB claim 과 low-evidence business-rule claim 은 모두 `REVIEW_REQUIRED` 로 남긴다
- PPM 접근 실패 시 PLF fallback 은 금지하고 `production_ready: false` 를 유지한다
- Java/MyBatis 는 `draft_only_readiness_notes` 로만 다루며 generated source application 은 수행하지 않는다

판정 해석:
- 통과: fixture-first renderer/evaluator report 가 모든 P24 threshold 를 만족하고 `productionReady: false`, storage safety findings 0, PLF fallback 없음, unsupported claim `REVIEW_REQUIRED` 를 유지한다.
- 보류: 필수 fixture-first gate 는 통과했지만 optional live confidence evidence 가 skip/fail/unavailable 이거나 로컬 검증 prerequisites 가 준비되지 않았다. 이는 confidence evidence 부족이며 production readiness 로 해석하지 않는다.
- 실패/blocker: threshold 미달, raw prompt/SP/provider response/row data/secret 저장, PPM-to-PLF fallback, `production_ready: true` 또는 자동 전환 완료 주장, automatic conversion/apply, row data 조회, procedure execution, business DB DDL/DML 요구, 또는 P25+ Java/MyBatis 확장을 P24 완료로 표현하는 경우다.

통과 기준:
- `required_section_coverage >= 1.0`
- `evidence_linked_claim_coverage >= 0.9`
- `dml_matrix_coverage >= 0.9`
- `branch_call_flow_coverage >= 0.85`
- `unsupported_claim_review_required_ratio >= 1.0`
- `storage_safety_findings <= 0`

```bash
make test PYTEST_ARGS="tests/eval/test_p24_sp_migration_guide_quality.py tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py"
```

### 12. P30 Metadata AI-MCP Analysis Gate

대상:
- `POST /api/v1/metadata/analyze`
- `fixtures/eval/metadata_ai_mcp_analysis_p30_v1.yaml`
- `tests/eval/test_p30_metadata_ai_mcp_analysis.py`

필수 체크:
- 기존 `GET /api/v1/metadata/search` 는 deterministic search 로 유지하고 LLM 호출을 기본 포함하지 않는다
- analyze API 는 `query` 또는 단일 `target` 중 하나만 받아 metadata analysis 응답을 생성한다.
  P34 이후 기본 실행은 sanitized knowledge asset 도 함께 저장한다
- `useLlmAnalysis=true`, `useAiToolOrchestration=true`, `maxTargets=3` 이 analyze API 기본값이다
- LLM planner 는 active/read-only MCP catalog 를 후보로 보지만 실행은 내부 registry/policy gate 로만 수행한다
- public metadata invoke API allowlist 는 `get_dependency_closure`, `resolve_dependency_reference` 로 유지한다
- response 는 sanitized `aiToolEvidence`, `deterministicFacts`, `mcp.<toolName>.<hash>` fact id,
  metadata insights, review markers 만 반환하고 raw SQL/definition, row data, procedure execution,
  DDL/DML, secret, raw prompt/provider response text 를 반환하지 않는다
- adversarial planner 가 write/free-form SQL/secret-like argument 를 요청하면 workflow failure 가 아니라
  `AI_METADATA_ANALYSIS_REVIEW_REQUIRED` marker 와 blocked request digest 로 남긴다

통과 기준:
- `make test PYTEST_ARGS="tests/unit/api/test_metadata_analysis_service.py tests/eval/test_p30_metadata_ai_mcp_analysis.py tests/integration/api/test_api_workflow_routes.py tests/contract/test_openapi_and_env_sample_assets.py tests/unit/web/test_p14_product_ui_static.py"` 통과
- optional live OpenAI/PPM confidence 는 별도 승인 환경에서만 판정하고, 기본 gate 는 fixture-first 로 유지한다

### 13. P31 Metadata Object Insight Depth Gate

대상:
- `POST /api/v1/metadata/analyze`
- `fixtures/eval/metadata_object_insight_depth_p31_v1.yaml`
- `tests/eval/test_p31_metadata_object_insight_depth.py`

필수 체크:
- analyze API 는 DB migration, persisted artifact, workflow state transition 을 추가하지 않는다.
  P34 이후 기본 실행은 sanitized knowledge asset persistence 를 수행한다
- TABLE 대상은 schema/constraints/indexes/extended properties/related objects evidence 로 `objectProfiles`, `insightGroups`, `dependencyGraph`, `dtoReadiness` 를 반환한다
- PROCEDURE/VIEW/FUNCTION 대상은 dependency/docs/related-object 중심으로 확장 가능하되 raw definition text 는 prompt/response/trace 에 남기지 않는다
- object profile 과 graph 요약은 `metadata.profile.<hash>` deterministic fact id 로 승격되고, LLM insight/dto claim 은 `mcp.*`, `metadata.profile.*`, `metadata.search.*` fact id 만 evidence 로 사용할 수 있다
- public metadata invoke API allowlist 는 계속 `get_dependency_closure`, `resolve_dependency_reference` 로 제한한다
- adversarial planner 가 write/free-form SQL/secret-like argument 를 요청하면 workflow failure 가 아니라 blocked request digest 와 review marker 로 남긴다
- raw SQL/definition, row data, procedure execution, DDL/DML, secret, raw prompt/provider response text 를 반환하지 않는다

통과 기준:
- `make test PYTEST_ARGS="tests/unit/api/test_metadata_analysis_service.py tests/eval/test_p30_metadata_ai_mcp_analysis.py tests/eval/test_p31_metadata_object_insight_depth.py tests/integration/api/test_api_workflow_routes.py tests/contract/test_openapi_and_env_sample_assets.py tests/unit/web/test_p14_product_ui_static.py"` 통과
- `make test-web-smoke` 통과
- optional live OpenAI/PPM confidence 는 별도 승인 환경에서만 판정하고, 기본 gate 는 fixture-first 로 유지한다

### 14. P32 Live Confidence + Planner Effectiveness Gate

P32 는 bounded AI-MCP planner 가 실제로 유용한 metadata evidence 를 수집하고 그 evidence 가 최종 claim 에
인용되는지를 fixture-first 로 측정한다. Live OpenAI+PPM 조합은 명시적 confidence gate 로만 실행한다.

대상:
- `aiToolEvidence.plannerMetrics`
- `fixtures/eval/live_confidence_planner_effectiveness_p32_v1.yaml`
- `tests/eval/test_p32_live_confidence_planner_effectiveness.py`

필수 체크:
- SP workflow trace 와 Metadata Analyze response 는 planned/executed/blocked/failed/deduped call count,
  evidence fact count, cited fact count, evidence utilization, claim support rate 를 sanitized summary 로 노출한다
- planner effectiveness 는 `mcp.*` 와 `metadata.profile.*` fact id 만 tool-grounded evidence 로 인정한다
- duplicate request 는 dedupe count 로 잡히고 중복 internal MCP invocation 을 만들지 않는다
- blocked unsafe request 와 individual tool failure 는 workflow failure 가 아니라 `REVIEW_REQUIRED` metrics/status 와 review marker 로 남긴다
- under-utilized planner evidence 는 `REVIEW_REQUIRED` metrics/status 로 잡힌다
- raw SQL/definition, row data, procedure execution, DDL/DML, secret, raw prompt/provider response text 를 반환하지 않는다
- `P32_LIVE_CONFIDENCE_GATE=1` 일 때만 remote LLM 과 live PPM metadata 를 결합한다. Env/profile/prerequisite 누락은 gate enabled 상태에서 blocker failure 이며, 기본 실행은 `NOT_RUN_CONFIDENCE_ONLY` 다
- P-GPT planner output 은 strict-first 로 검증하고 safe aliases (`tools`, `args`, `rationale`, `evidenceUse`) 만 canonical `toolRequests`, `arguments`, `reason`, `expectedEvidenceUse` 로 정규화한다. Invalid/empty planner output 에서는 TABLE 과 PROCEDURE/VIEW/FUNCTION 대상별 deterministic read-only fallback request 를 만들되 기존 `AgentToolPolicy`, budget, dedupe, sanitizer 를 반드시 통과해야 한다.
- live confidence 성공은 production readiness 가 아니라 confidence signal 이며 `production_ready: false` 를 유지한다

통과 기준:
- `make test PYTEST_ARGS="tests/unit/agent_runtime/test_planner_effectiveness.py tests/unit/api/test_metadata_analysis_service.py tests/eval/test_p32_live_confidence_planner_effectiveness.py tests/integration/api/test_api_workflow_routes.py tests/contract/test_openapi_and_env_sample_assets.py tests/unit/web/test_p14_product_ui_static.py"` 통과
- 선택 live: `P32_LIVE_CONFIDENCE_GATE=1 LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 MSSQL_ENABLE_LIVE_METADATA=1 MSSQL_METADATA_CONNECT_TIMEOUT_SECONDS=20 make test PYTEST_ARGS="tests/eval/test_p32_live_confidence_planner_effectiveness.py"`

### 15. P33 Performance / Scale Fixture-First Gate

P33 은 live PPM latency/cost 흔들림을 줄이기 위한 process-local 최적화 경계를 검증한다. 기본 구현은
DB migration, queue infra, 새 runtime dependency 없이 fixture-first 로 동작한다.

대상:
- `MCP_TOOL_RESULT_CACHE_ENABLED`, `MCP_TOOL_RESULT_CACHE_TTL_SECONDS`,
  `MCP_TOOL_RESULT_CACHE_MAX_ENTRIES`
- `WORKFLOW_MAX_ACTIVE_JOBS`, `MSSQL_METADATA_MAX_CONCURRENCY`, `BACKPRESSURE_WAIT_MS`
- `AI_TOOL_MAX_CALLS`, `AI_TOOL_MAX_ROUNDS`, `AI_TOOL_LIVE_MAX_ROUNDS`
- `POST /api/v1/requests/sp-analysis/batch`
- `fixtures/eval/performance_scale_p33_v1.yaml`
- `tests/eval/test_p33_performance_scale.py`

필수 체크:
- active/read-only MCP tool 성공 응답만 TTL/LRU process-local cache 에 저장한다
- cache key 는 sanitized arguments, profile/database, live/fixture repository identity, catalog version 을
  포함하고, trace 에는 `cacheStatus`, `cacheKeyHash`, `cacheAgeMs` 만 남긴다
- raw SQL/definition text, row data, secret-like values, failed/write-like calls 는 cache 저장 대상이 아니다
- `mcp.<toolName>.<hash>` fact id 는 volatile `snapshotId`/`collectedAt` 이 아니라 sanitized content 와
  argument hash 기반 `contentHash` 로 안정화한다
- `aiToolEvidence.plannerMetrics` 는 `cacheHitCount` 와 `cacheMissCount` 를 포함한다
- batch SP endpoint 는 max target cap, duplicate target dedupe, accepted/rejected summaries 를 반환하고
  persisted batch table 을 만들지 않는다
- workflow/MCP capacity 초과는 각각 `WORKFLOW_BACKPRESSURE`, `MCP_BACKPRESSURE` 로 표시한다
- live PPM planner round 는 기본 `AI_TOOL_LIVE_MAX_ROUNDS=1` 로 줄이고 `AI_TOOL_BUDGET_REDUCED` marker 를 남긴다

통과 기준:
- `make test PYTEST_ARGS="tests/unit/api/test_metadata_tool_cache.py tests/unit/api/test_workflow_service.py tests/unit/api/test_metadata_analysis_service.py tests/unit/api/test_batch_sp_analysis.py tests/integration/api/test_api_workflow_routes.py tests/eval/test_p33_performance_scale.py tests/contract/test_openapi_and_env_sample_assets.py tests/unit/web/test_p14_product_ui_static.py"` 통과
- `make test-web-smoke` 통과

### 16. P34 Knowledge Assetization Fixture-First Gate

P34 는 SP 분석, dependency evidence, metadata profile, DTO readiness 를 일회성 응답/trace 에서
sanitized versioned knowledge asset, fact graph, export 로 승격한다. v5 DDL 은 저장소에 추가만 하고
실제 DB 적용은 운영자의 수동 절차로 둔다.

대상:
- `db/schema/ai_agent_platform_schema_v5_knowledge_assets.sql`
- `GET /api/v1/jobs/{jobId}/knowledge-assets`
- `GET /api/v1/knowledge/assets/{assetId}`
- `GET /api/v1/knowledge/assets/{assetId}/versions`
- `GET /api/v1/knowledge/assets/{assetId}/versions/{versionId}/facts`
- `POST /api/v1/knowledge/exports`
- `fixtures/eval/knowledge_assetization_p34_v1.yaml`
- `tests/eval/test_p34_knowledge_assetization.py`

필수 체크:
- `persistKnowledge=true` 가 SP analysis 와 Metadata Analyze 의 기본값이다
- `KNOWLEDGE_ASSETIZATION_ENABLED=0` 이면 persistence 를 skip marker 로 남길 수 있다
- SP workflow 는 `SP_ANALYSIS`, `DEPENDENCY_EVIDENCE`, `METADATA_PROFILE`, `DTO_READINESS`,
  `CANONICAL_ANALYSIS` summaries 를 job knowledge API 로 조회 가능해야 한다
- Metadata Analyze 는 response 에 `knowledgeAssets[]` 를 포함하고 fact endpoint 에서 `mcp.*` /
  `metadata.profile.*` refs 를 조회 가능해야 한다
- 동일 logical asset key 에서 같은 `contentHash` 는 version 을 재사용하고, content 변경 시에만
  새 version 을 만든다
- 같은 logical asset/contentHash 를 여러 job 이 재사용해도 `KNOWLEDGE_ASSET_JOB_LINKS` 기반으로
  각 job 의 `knowledge-assets` 조회 결과가 유지된다
- fact graph edge 의 `fromFactId`/`toFactId` 는 같은 asset version 의 실제 fact id 를 참조하며,
  edge endpoint 를 확인할 수 없으면 `REVIEW_REQUIRED` endpoint fact 로 남긴다
- `POST /api/v1/knowledge/exports` 의 `versionIds` 는 비어 있거나 `assetIds` 와 같은 길이여야 하며,
  불일치 시 `KNOWLEDGE_EXPORT_VERSION_SELECTION_INVALID` 를 반환한다
- JSONL export 는 fact one-line-per-record, GRAPH_JSON export 는 nodes/edges/contentHash 를 포함한다
- raw SP definition, SQL text, row data, secret, raw prompt/provider response text 와 raw-derived
  redaction hash/length 는 storage, API, export, Web summary 에 남지 않는다
- Platform DB adapter 는 v6 필수 table 이 없으면 `KNOWLEDGE_SCHEMA_REQUIRED` 로 실패하고,
  Metadata Analyze API 는 503 JSON error 로 반환하며, API 가 DDL 을 자동 적용하지 않는다
- P35 uses the v6 manual-apply draft with lifecycle readiness: `KNOWLEDGE_ASSET_VERSIONS`
  carries `DRAFT`, `REVIEW_REQUIRED`, `ARCHIVED` state.
- New content versions start `DRAFT`; same `contentHash` reuse preserves lifecycle; changed
  content creates a new `DRAFT` version even when the previous version had evidence caveats.
- Human review API transitions are absent. `ARCHIVED` is terminal and returns
  `KNOWLEDGE_LIFECYCLE_TRANSITION_INVALID` on invalid lifecycle mutation.
- Asset search and fact search default to excluding `ARCHIVED`; explicit
  `lifecycleStatus=ARCHIVED` includes archived versions. Fact search without a meaningful filter
  returns `KNOWLEDGE_SEARCH_FILTER_REQUIRED`.
- `REVIEW_REQUIRED` remains an evidence caveat and is not production-ready, publish approval,
  deployment approval, human review request, or automatic conversion approval evidence.

통과 기준:
- `make test PYTEST_ARGS="tests/unit/api/test_knowledge_asset_service.py tests/unit/api/test_workflow_service.py tests/unit/api/test_metadata_analysis_service.py tests/integration/api/test_api_workflow_routes.py tests/integration/api/test_api_auth_rbac.py tests/contract/test_openapi_and_env_sample_assets.py tests/eval/test_p34_knowledge_assetization.py tests/unit/web/test_p14_product_ui_static.py"` 통과
- `make test-web-smoke` 통과

### 16B. P35 Knowledge Live Confidence Gate

P35 live confidence is explicit and disabled by default. `P35_KNOWLEDGE_LIVE_GATE=1`
combines live OpenAI, read-only `ppm`/`PPM` metadata, and live PLF knowledge persistence after
operators manually apply v6 DDL. Missing env, missing `ppm -> PPM` profile mapping, or missing v6
knowledge schema objects are blocker failures, not skips.

Required checks:
- Disabled mode must not initialize PLF, PPM, or OpenAI access.
- Live mode submits one bounded PPM SP workflow with `persistKnowledge=true`, validates OpenAI
  semantic analysis used the configured remote provider, and verifies job-linked knowledge assets
  for `SP_ANALYSIS`, `DEPENDENCY_EVIDENCE`, `METADATA_PROFILE`, `DTO_READINESS`, and
  `CANONICAL_ANALYSIS`.
- Fact graph edges must reference persisted fact ids in the same version; asset/fact search and
  GRAPH_JSON export must return sanitized knowledge without raw SQL/SP text, row data, secrets,
  raw prompt, or raw provider response text.
- The gate verifies search/export confidence without writing human review records. It must not
  archive real PPM knowledge; archived terminal behavior remains fixture/unit coverage.
- If `AUTH_RBAC_ENFORCEMENT=1`, live auth confidence uses `OIDC_USER_BEARER_TOKEN` and verifies
  the token resolves to an active PLF actor; no reviewer token or review write is required.
- Passing this gate is confidence evidence only. It does not make knowledge production-ready,
  authorize publish/deploy, or approve automatic conversion.

Run:
```bash
P35_KNOWLEDGE_LIVE_GATE=1 LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1 MSSQL_ENABLE_LIVE_METADATA=1 MSSQL_METADATA_CONNECT_TIMEOUT_SECONDS=20 PLATFORM_DB_CONNECT_TIMEOUT_SECONDS=20 make test PYTEST_ARGS="tests/eval/test_p35_knowledge_live_confidence_gate.py"
```

### 17. P27 Dependency Evidence Tooling Fixture-First Hardening Contract

P27 은 dependency evidence 계약을 fixture-first MCP 구현과 명시적 hard-live gate 로 강화한다.
목표는 AI-heavy semantic analysis 와 P24 guide renderer 에 raw SQL 이 아닌 구조화된
dependency evidence digest 를 공급할 수 있도록 deterministic metadata 층을 강화하는 것이다.

대상:
- `spec/mcp/mssql_metadata_tool_catalog.yaml`
- `spec/eval/p27_dependency_evidence_tooling_contract.yaml`
- `tests/unit/test_mcp_catalog.py`
- `tests/unit/mcp/test_tool_registry.py`
- `tests/contract/mcp/test_tool_invocation_contract.py`
- `tests/eval/test_p27_dependency_evidence_hard_live_gate.py`
- `tests/unit/api/test_metadata_service.py`
- `tests/integration/api/test_api_workflow_routes.py`

필수 체크:
- 기존 `get_procedure_dependencies` 계약은 `resolutionStatus`, `resolutionStrategy`, `sourceScope` 를 유지하고 `resolutionConfidence`, `resolutionEvidenceKind`, `unresolvedReason`, `resolutionChain` 을 optional structured evidence 로 선언한다
- `get_dependency_closure` 와 `resolve_dependency_reference` 는 active, read-only, structured-input-only MCP tool 로 catalog 에 존재하고 fixture/live repository handler 를 가진다
- `get_dependency_closure` 는 `maxDepth <= 3` 을 validator 로 강제하고, `includeReviewRequired=false` 일 때도 review-required dependency 를 `unresolved` 에 보존한다
- `resolve_dependency_reference` 는 전체 candidate set 이 정확히 하나이고 해당 candidate 가 `CONFIRMED` + `HIGH` 일 때만 `selectedResolution` 을 채운다
- fixture/mocked-live test 는 confirmed, synonym, caller-dependent, dynamic SQL, cross-server, ambiguous, unresolved dependency 를 구분해 deterministic promotion 경계를 검증한다
- standard MCP response envelope 은 `snapshotId`, `collectedAt`, `evidenceRefs` 를 계속 요구한다
- confirmed dependency 만 deterministic fact 로 승격 가능하며, ambiguous/dynamic/cross-server/unconfirmed synonym/caller-dependent reference 는 `REVIEW_REQUIRED` 를 유지한다
- raw SP definition, raw prompt, raw provider response, row data, procedure execution, business DB DDL/DML, free-form SQL input, PPM-to-PLF fallback 은 계속 금지한다
- P28 기준 `/api/v1/metadata/tools/{toolName}/invoke` 는 `get_dependency_closure` 와
  `resolve_dependency_reference` 만 안전하게 호출한다. P29 기준 `/metadata/dependencies`
  Web diagnostic UI 는 이 route 를 수동 진단용으로 사용하고, runtime workflow 는 PROCEDURE
  target 에 대해 `get_dependency_closure` evidence digest 만 자동 병합한다. persisted artifact
  type 변경, DB schema 변경, default live gate 요구는 계속 포함하지 않는다
- bounded AI tool orchestration 은 public invoke API 를 넓히지 않고, 내부 workflow 에서만 active/read-only
  catalog 전체를 후보로 사용한다. free-form SQL/write-like/profile-switch/row-data/secret-like
  요청은 blocked request 와 `AI_TOOL_ORCHESTRATION_REVIEW_REQUIRED` marker 로 남겨야 한다.
- P29B 기준 DB migration, 새 persisted artifact type, workflow state transition 은 deferred 로
  확정한다. dependency evidence 는 기존 metadata collection payload 의 sanitized
  `dependencyEvidence` digest 와 기존 draft artifact evidence refs/rendered section 으로만
  전달한다.
- `P27_HARD_LIVE_GATE=1` 로 명시 실행한 경우에만 `selected_objects.yaml` 의 PPM simple/medium/complex procedure 를 대상으로 hard-live closure/resolver gate 를 수행한다. 이때 PPM profile/env 누락, template-only manifest, PPM 접근 실패, PLF fallback 은 blocker failure 다
- 로컬 host-run 에서 Chakra/legacy proxy 가 `python-tds` 기본 TDS negotiation 을 거부하는 경우 `MSSQL_METADATA_TDS_VERSION=7.0` 으로 명시할 수 있으며, 기본값은 `7.4` 이다

판정 해석:
- 통과: active/read-only/structured tool 계약, fixture/live handler, API summary 노출, dependency item evidence 확장, no-raw/no-row/no-fallback policy 가 문서와 테스트에서 일치한다.
- 보류: default fixture-first hardening 은 통과했지만 explicit P27 hard-live gate 가 skip/unavailable 이거나 로컬 PPM prerequisites 가 준비되지 않았다. 이는 production readiness 로 해석하지 않는다.
- 실패/blocker: P27 tool 이 inactive/writable/handler 없는 상태가 되거나, 자유 SQL/row data/procedure execution/DDL/DML/raw definition storage/PLF fallback 을 허용하거나, 불확실 dependency 를 deterministic fact 로 승격하거나, `P27_HARD_LIVE_GATE=1` 상태에서 missing prerequisites 를 skip 하는 경우다.

```bash
make test PYTEST_ARGS="tests/unit/test_mcp_catalog.py tests/unit/mcp/test_tool_registry.py tests/contract/mcp/test_tool_invocation_contract.py tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py tests/unit/api/test_metadata_service.py tests/unit/api/test_ai_tool_orchestrator.py tests/unit/api/test_route_surface.py tests/integration/api/test_api_workflow_routes.py tests/contract/test_openapi_and_env_sample_assets.py"
P27_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 MSSQL_METADATA_CONNECT_TIMEOUT_SECONDS=20 make test PYTEST_ARGS="tests/eval/test_p27_dependency_evidence_hard_live_gate.py"
```

## 초기 fixture 세트

`fixtures/` 아래에 최소 아래 대표 사례를 둔다.

1. `sp_simple_crud`
   - 단순 입력/출력
   - 기본 CRUD 패턴

2. `sp_txn_with_try_catch`
   - 명시적 transaction
   - TRY/CATCH

3. `sp_with_dynamic_sql`
   - dynamic SQL 탐지
   - review_required 경계

4. `sp_with_temp_table`
   - temp table 사용
   - intermediate result 추론

5. `schema_search_order_domain`
   - 주문 도메인 테이블/컬럼 유사 검색
   - logical/physical name mapping

## PR / 작업 단위 최소 게이트

| 변경 종류 | 최소 검증 |
|---|---|
| 문서만 변경 | 링크/예시/명령 검토 |
| API contract 변경 | schema validation + contract test |
| MCP tool 변경 | contract test + read-only enforcement test |
| parser/analysis 변경 | fixture 기반 analysis eval |
| generator 변경 | artifact format eval + evidence coverage |
| 작업자-facing 언어 변경 | `artifact.localized_human_text.ko_kr` validation + generator/API unit |
| policy/draft validation 변경 | workflow state test + quality caveat assertions |
| auth/RBAC source 변경 | ADR/admin guide sync + role matrix contract test |
| auth/RBAC enforcement 변경 | 401/403 negative route test + audit actor binding test |
| OpenAI/LLM runtime 변경 | fake gateway unit + no-raw-trace contract + optional live gate 문서화 |
| LLM analysis quality eval 변경 | P23 contract prompt asset test + fixture-first fake eval + optional live gate 문서화 |
| SP migration guide quality eval 변경 | P24 contract prompt asset test + fixture-first renderer/evaluator section/evidence/DML/call-flow eval |
| Dependency evidence tooling 변경 | MCP catalog contract + active read-only handler/API summary/no-raw policy test |

## 평가 산출물 형식

가능하면 각 평가 실행은 아래 구조의 JSON 또는 동등한 구조를 남긴다.

```json
{
  "suite": "analysis-model-accuracy",
  "fixture": "sp_txn_with_try_catch",
  "status": "pass",
  "metrics": {
    "required_fields_present": true,
    "exact_match_fields": 12,
    "review_required_fields": 2
  },
  "artifacts": [
    "analysis_result.json",
    "validation_report.json"
  ]
}
```

현재 P06 eval fixture 는 `fixtures/eval/` 아래 file-based interface 로 둔다.

- `request.json`
- `canonical_analysis_candidate.json`
- `artifact_payloads.json`
- `rubric.yaml`

## 완료 판정

아래를 모두 만족해야 완료다.

- 필수 평가 스위트 통과
- 정책 위반 없음
- 문서 동기화 완료
- 남은 리스크가 명시됨
- 사람이 검토해야 하는 부분이 분리되어 제시됨

## 테스트 실행 환경

- 기본 검증 경로는 `docker/test/` 아래의 도커 테스트 러너다.
- Python 실행 기준은 host 와 Docker 모두 3.14 이다.
- `make test` 와 이를 호출하는 `make check` 는 호스트 직접 실행 대신 컨테이너 기반 실행을 우선한다.
- 외부 DB 가 필요한 테스트는 환경변수로 연결하되, 저장소는 해당 DB 의 lifecycle 을 관리하지 않는다.
- 자동 테스트가 아직 없는 영역은 smoke/build 검증과 테스트 공백 보고를 함께 남긴다.
