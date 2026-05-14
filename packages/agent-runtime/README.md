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
- Semantic analysis now runs through per-SP tasks. Multiple SP tasks can fan out with `LLM_SP_CONCURRENCY` (default `2`), while the public single-SP API stays unchanged.
- P26 high-quality mode is the API/Web default. Each SP task uses staged calls for deterministic evidence digest, business rule extraction, Java/MyBatis conversion readiness, migration guide insights, evidence criticism, plus at most one repair call when evidence refs or required markers are missing.
- The runtime constrains live structured-output schemas with the task's deterministic fact ids, repairs stored output so claim `evidenceRefs` do not use prompt/input/output hashes, and injects a `LLM_OUTPUT_STORAGE_SANITIZED` review marker when unsafe model text is removed.

## Registry refs

- `model:openai_sp_semantic_analysis@0.1.0`; `OPENAI_MODEL_ANALYSIS` changes the live high-quality model.
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
