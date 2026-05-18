---
name: framework-adapter-pilot
description: Plan, review, and improve the adopted P44+ framework runtime path. Use when Codex works on OpenAI Agents SDK, LangGraph, AiGenerationFrameworkAdapter, rollback, live evidence, or generic AI Draft Pack quality while preserving P42 gates, public surface freeze, benchmark-not-answer-key behavior, and production_ready false.
---

# Framework Runtime Quality

## Workflow

1. Read the current decision and policy evidence first:
   - `spec/eval/p44_framework_runtime_adoption_contract.yaml`
   - `spec/eval/p46_rollback_removal_decision.yaml`
   - `docs/framework-adoption-decision-p43.md`
   - `spec/eval/p43_framework_adoption_contract.yaml`
   - `POLICY.md`
2. Treat P44 as actual internal framework adoption: OpenAI Agents SDK for OpenAI remote AI Draft Pack generation and LangGraph for in-process orchestration behind `AiGenerationFrameworkAdapter.v0.1`.
3. Keep `responses_httpx` only as P-GPT compatibility and emergency rollback, not as the active OpenAI default.
4. Route every output through `AiJavaMyBatisDraftPack.v0.1`, deterministic inventory checks, repair, and P42 Java/MyBatis quality gates.
5. Improve quality through generic evidence coverage, prompt design, tool evidence, model selection, and validation logic, not benchmark-specific hardcoding.

## Runtime Gates

- Do not add request flags, environment switches, public API fields, DB schema, UI, public MCP routes, or public artifact types.
- Do not store raw prompts, raw provider responses, raw SP definitions, raw guide body, row data, secrets, failed Java/XML payloads, or unredacted framework traces.
- Do not allow procedure execution, row-data queries, business DB DDL/DML, source apply, deploy, publish, or automatic conversion.
- Keep weak or unsupported framework-inferred facts as `REVIEW_REQUIRED`.
- Keep `production_ready` false until a separate production-readiness gate exists.
- Treat named procedures such as ManageBond as benchmark signals only, never runtime answer keys.

## Output Checklist

- Runtime framework id and version/source assumptions are documented.
- Rollback path is explicit and tested as emergency/P-GPT only.
- Fixture-first replay passes before optional live evidence is interpreted.
- Generic coverage evidence is preferred over ManageBond-specific DTO or method hardcoding.
- Failure diagnostics are sanitized, stage-specific, and do not include raw payloads.
