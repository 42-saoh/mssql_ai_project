# Task
- ID: P26
- Title: AI-heavy hybrid SP analysis
- Priority: High
- Owner: Codex
- Requested by: User

## Goal

Shift the default SP analysis posture from tool-only enrichment to tool-grounded AI-heavy hybrid analysis. Deterministic metadata/static analysis remains the evidence layer, while high-quality LLM semantic analysis strengthens migration guide quality and Java/MyBatis conversion readiness. `production_ready: false` remains unchanged.

## In Scope

- API and Web default request options:
  - `useLlmAnalysis=true`
  - `allowSpDefinitionToModel=true`
  - `llmProfileId=openai_sp_semantic_analysis`
- Transient full SP definition input to the model, without storing or returning raw prompt, raw SP definition, or raw provider response text.
- Staged semantic runtime:
  - deterministic evidence digest
  - business rule extraction
  - Java/MyBatis conversion readiness
  - migration guide insights
  - evidence critic / repair
- LLM output schema extension with `conversionGuidance` and `migrationGuideInsights`.
- Fixture-first eval scoring for guide/conversion recall.
- Documentation and contract synchronization.

## Out of Scope

- Runtime publish/export/deploy.
- Procedure execution, row data access, business DB DDL/DML, or automatic Java/MyBatis source application.
- New persisted artifact types.
- Production readiness claims.
- PPM-to-PLF fallback.

## Verification

- `make test PYTEST_ARGS="tests/unit/agent_runtime tests/unit/api tests/integration/api tests/eval tests/contract"`
- `make test-web-smoke`
- `git diff --check`

## Notes / Risks

- Default fixture tests must keep using `FakeModelGateway`; optional live OpenAI runs require `LLM_ENABLE_REMOTE=1`, `LLM_ALLOW_SP_TEXT=1`, and `OPENAI_API_KEY`.
- Optional live confidence failures are quality evidence failures, not production blockers.
