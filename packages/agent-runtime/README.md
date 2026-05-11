# packages/agent-runtime

OpenAI LLM agent runtime slice for P22.

## Boundary

- Workflow orchestrator owns job state and calls this package after metadata collection and deterministic analysis.
- `FakeModelGateway` is the default test/local adapter and never calls OpenAI.
- `OpenAIModelGateway` calls the OpenAI Responses API only when `LLM_ENABLE_REMOTE=1`.
- SP definition text may be sent as transient model input only when `LLM_ALLOW_SP_TEXT=1` and the request option `allowSpDefinitionToModel=true`.
- Raw prompt text, raw SP definition text, and raw provider response text are not returned in storage payloads.
- Semantic analysis now runs through per-SP tasks. Multiple SP tasks can fan out with `LLM_SP_CONCURRENCY` (default `2`), while the public single-SP API stays unchanged.
- P26 high-quality mode is the API/Web default. Each SP task uses staged calls for deterministic evidence digest, business rule extraction, Java/MyBatis conversion readiness, migration guide insights, evidence criticism, plus at most one repair call when evidence refs or required markers are missing.
- The runtime constrains live structured-output schemas with the task's deterministic fact ids and repairs stored output so claim `evidenceRefs` do not use prompt/input/output hashes.

## Registry refs

- `model:openai_sp_semantic_analysis@0.1.0`; `OPENAI_MODEL_ANALYSIS` changes the live high-quality model.
- `model:openai_fast_test@gpt-5-nano@0.1.0` by default; `OPENAI_MODEL_FAST_TEST` changes the runtime registry ref for manual fast/test runs.
- `prompt:sp_semantic_analysis@0.3.0`
- `schema:llm_semantic_analysis@0.3.0`
