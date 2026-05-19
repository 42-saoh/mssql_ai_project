# packages/agent-runtime

OpenAI LLM agent runtime slice for P22.

## Boundary

- Workflow orchestrator owns job state and calls this package after metadata collection and deterministic analysis.
- `FakeModelGateway` is the default test/local adapter and never calls OpenAI.
- `OpenAIModelGateway` calls the official OpenAI Responses API only when `LLM_ENABLE_REMOTE=1` and `LLM_REMOTE_PROVIDER` is unset or `openai`.
- `LLM_REMOTE_PROVIDER=pgpt` uses the private P-GPT `/v1/responses` contract with the minimal Postman-verified body: `model`, `instructions`, and message-array `input`; no `stream`, `max_output_tokens`, `text.format`, or `reasoning`.
- P-GPT resolves `OPENAI_RESPONSES_URL` first, otherwise it appends `/v1/responses` to `OPENAI_BASE_URL` unless that base already ends in `/v1`.
- SP definition text may be sent as transient model input only when `LLM_ALLOW_SP_TEXT=1` and the request option `allowSpDefinitionToModel=true`.
- Raw prompt text, raw SP definition text, and raw provider response text are not returned in storage payloads. Stored structured output is also sanitized before persistence if a model echoes procedure text, raw trace markers, row-data markers, or secret-like assignments.
- Remote semantic output is strict-validated first. If a provider returns schema-drifted JSON, the runtime deterministically removes unsupported fields, normalizes safe text aliases such as `text` to the canonical summary fields, coerces unsupported claim statuses back to `INFERRED_DESCRIPTION` or `REVIEW_REQUIRED`, and records only sanitized normalizer metadata without raw provider text.
- When `LLM_REMOTE_PROVIDER=pgpt`, semantic analysis also applies a deterministic safety net after model repair and before storage sanitization. It adds only draft/reviewable claims linked to allowed deterministic fact ids, using `DETERMINISTIC_SAFETY_NET_*` keys, so P23 quality recall can improve without raw prompt/provider/SP text or widened schemas.
- `ModelGateway.plan_metadata_tools` provides the bounded tool-planning call. It returns strict JSON tool requests only; provider aliases such as `tools`, `args`, or `rationale` are normalized to `toolRequests`, `arguments`, and `reason` before validation. The API workflow executes allowed MCP tools and stores only sanitized tool evidence summaries.
- `ModelGateway.plan_platform_tools` provides the bounded platform context tool-planning call. It uses the same strict tool request shape, but the API workflow executes only internal read-only platform tools scoped to the current job, db profile, and target, then stores sanitized `platformToolEvidence` summaries.
- `ModelGateway.analyze_metadata` provides response-only metadata analysis for `POST /api/v1/metadata/analyze`. It uses strict JSON structured output constrained to deterministic fact ids and does not store raw prompt, raw definition, row data, or provider response text.
- `ModelGateway.draft_ai_java_mybatis_pack` provides the P42 `AiJavaMyBatisDraftPack.v0.1` structured-output path for draft-only Java/MyBatis file bundles. It uses the existing Responses/httpx gateway, stores only schema-valid structured output and trace hashes, keeps `productionReady=false`, and relies on downstream deterministic validation before workflow artifact persistence.
- P43 adds `AiGenerationFrameworkAdapter.v0.1` as an internal-only adapter contract around AI Draft Pack inventory, file-content, repair, and trace-summary stages. P43 is now historical readiness evidence; P49 supersedes the production-exported baseline/fake adapter scaffolding while retaining Responses/httpx as a gateway rollback path.
- P43F records the historical framework decision as `pilot`. P44 supersedes it with actual internal runtime adoption after dependency approval and trace/persistence gates; the same P42 schema/inventory/static-quality gates still apply.
- P44 supersedes that pilot as the active runtime direction. `FrameworkRuntimeConfig.v0.1` selects `OpenAIAgentsFrameworkAdapter` plus `LangGraphAiDraftPackOrchestrator` for OpenAI remote AI Draft Pack runs. P-GPT AI Draft Pack generation defaults to `responses_httpx` for compatibility, but an explicit internal `AI_GENERATION_RUNTIME=openai_agents` selection may use the OpenAI Agents SDK with an approved P-GPT-compatible endpoint and post-run P42 validation.
- OpenAI Agents SDK tracing is disabled before stage execution and stored summaries are limited to hashes, counts, stage names, model/profile ids, token counts, component ids, blocker ids, and sanitized failure codes. LangGraph compiles without a persistent checkpointer; graph state is transient and the platform DB remains the persistence boundary.
- P44 adds no public API, DB schema, UI, public MCP route, or public artifact type. Generated artifacts remain draft-only with `productionReady=false` / `production_ready: false`; procedure execution, row data access, source apply, deploy, raw prompt/provider response storage, raw SP definition storage, raw guide body storage, and secrets remain forbidden.
- P45 adds the optional `P44_OPENAI_AGENTS_LIVE_GATE=1` confidence gate for the adopted OpenAI Agents runtime. The gate accepts either official OpenAI or approved P-GPT-compatible SDK evidence when trace locks, explicit runtime selection, sanitized fixture inputs, and post-run P42 validation are present. P46 keeps `responses_httpx` out of the OpenAI default path but retained for P-GPT default compatibility and emergency rollback; deletion requires a later cleanup gate.
- P47 upgrades the AI Draft Pack prompt to `prompt:ai_java_mybatis_draft_pack@0.2.0` and renders `DraftPackEvidenceBundle.v0.1` with generic operation coverage, DTO responsibility, review marker, and mapper coverage matrices. ManageBond names remain benchmark metrics only, not runtime answer keys.
- `openai_ai_draft_pack` is the high-quality live profile for AI Draft Pack generation. `OPENAI_MODEL_AI_DRAFT_PACK` falls back to `OPENAI_MODEL_ANALYSIS`, and `OPENAI_REASONING_EFFORT_AI_DRAFT_PACK` controls reasoning effort for the adopted OpenAI Agents path.
- P47 applies the deterministic DTO reference guard to every successful AI Draft Pack output, not only repair retries, so Service/Mapper/XML drafts keep generic DTO responsibility references required by the P42 validator.
- P45 live evidence accepts an official OpenAI Agents endpoint (`OPENAI_BASE_URL` empty or `https://api.openai.com/v1`) or an approved P-GPT-compatible endpoint configured with `OPENAI_BASE_URL` or `OPENAI_RESPONSES_URL`. Compatible endpoints use `OPENAI_AGENTS_COMPATIBLE_API=responses` by default, keep native SDK `output_type` disabled, and rely on immediate `AiJavaMyBatisDraftPack.v0.1` plus P42 quality validation.
- P48 adds `AiStructuredFrameworkAdapter.v0.1` and `FrameworkModelGateway` so OpenAI remote structured LLM calls for semantic analysis, metadata tool planning, metadata analysis, platform tool planning, and SP operation-model planning run through `OpenAIAgentsStructuredAdapter`. AI Draft Pack remains on the P44 `OpenAIAgentsFrameworkAdapter` plus LangGraph workflow path.
- P48 defaults remote structured calls to `openai_agents` for both official OpenAI and P-GPT-compatible endpoints. Setting `AI_STRUCTURED_LLM_RUNTIME=responses_httpx` keeps an explicit emergency rollback path for structured calls; AI Draft Pack keeps the P44 generation routing.
- P48 preserves evidence-ref repair, planner fallback, tool allowlists, SP source text gates, metadata/design sanitization, knowledge persistence sanitization, and `REVIEW_REQUIRED` behavior. The metadata design planner prompt metadata includes `toolNames` for remote structured validation.
- P48 adds no public API, DB schema, UI, public MCP route, public artifact type, source apply, deploy, row data access, procedure execution, or production readiness claim.
- P49 makes `p49_framework_runtime_consolidation_cleanup@0.1.0` the cleanup index for P43-P48 framework runtime evidence. P48 remains the active structured LLM runtime, P44 remains the active AI Draft Pack OpenAI Agents plus LangGraph runtime, and P43 is historical evidence only.
- P49 removes production exports for P43 baseline/fake framework adapter scaffolding. Equivalent fakes live under test helpers only. `responses_httpx` and `OpenAIModelGateway` remain retained for P-GPT AI Draft Pack compatibility and explicit emergency rollback, not as the default structured runtime.
- P49 adds no public API, DB schema, UI, public MCP route, public artifact type, source apply, deploy, row data access, procedure execution, or production readiness claim.
- Semantic analysis now runs through per-SP tasks. Multiple SP tasks can fan out with `LLM_SP_CONCURRENCY` (default `2`), while the public single-SP API stays unchanged.
- P26 high-quality mode is the API/Web default. Each SP task uses staged calls for deterministic evidence digest, business rule extraction, Java/MyBatis conversion readiness, migration guide insights, evidence criticism, plus at most one repair call when evidence refs or required markers are missing.
- The runtime constrains live structured-output schemas with the task's deterministic fact ids, repairs stored output so claim `evidenceRefs` do not use prompt/input/output hashes, and injects a `LLM_OUTPUT_STORAGE_SANITIZED` evidence caveat when unsafe model text is removed.

## Registry refs

- `model:openai_sp_semantic_analysis@0.1.0`; `OPENAI_MODEL_ANALYSIS` changes the live high-quality model.
- `model:openai_ai_draft_pack@0.1.0`; `OPENAI_MODEL_AI_DRAFT_PACK` and `OPENAI_REASONING_EFFORT_AI_DRAFT_PACK` change the live AI Draft Pack model path.
- `model:openai_fast_test@gpt-5-nano@0.1.0` by default; `OPENAI_MODEL_FAST_TEST` changes the runtime registry ref for manual fast/test runs.
- `PGPT_MODEL_ANALYSIS=gpt-4o` and `PGPT_MODEL_FAST_TEST=gpt-4o-mini` are provider-specific defaults when `LLM_REMOTE_PROVIDER=pgpt`.
- `prompt:sp_semantic_analysis@0.4.1`
- `schema:llm_semantic_analysis@0.4.1`
- `prompt:mssql_metadata_tool_planner@0.1.0`
- `schema:mssql_metadata_tool_plan@0.1.0`
- `prompt:platform_tool_planner@0.1.0`
- `schema:platform_tool_plan@0.1.0`
- `prompt:mssql_metadata_analysis@0.1.1`
- `schema:mssql_metadata_analysis@0.1.1`
- `prompt:ai_java_mybatis_draft_pack@0.2.0`
- `schema:ai_java_mybatis_draft_pack@0.1.0`
- `adapter:AiStructuredFrameworkAdapter.v0.1`
- `runtime:FrameworkModelGateway@0.1.0`
