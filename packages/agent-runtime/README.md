# packages/agent-runtime

OpenAI LLM agent runtime slice for P22.

## Boundary

- Workflow orchestrator owns job state and calls this package after metadata collection and deterministic analysis.
- `FakeModelGateway` is the default test/local adapter and never calls OpenAI.
- `OpenAIModelGateway` calls the OpenAI Responses API only when `LLM_ENABLE_REMOTE=1`.
- SP definition text may be sent as transient model input only when `LLM_ALLOW_SP_TEXT=1` and the request option `allowSpDefinitionToModel=true`.
- Raw prompt text, raw SP definition text, and raw provider response text are not returned in storage payloads.

## Registry refs

- `model:openai_sp_semantic_analysis@0.1.0`
- `model:openai_fast_test@gpt-5-nano@0.1.0`
- `prompt:sp_semantic_analysis@0.1.0`
- `schema:llm_semantic_analysis@0.1.0`
