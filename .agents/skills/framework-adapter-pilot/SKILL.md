---
name: framework-adapter-pilot
description: Plan and implement internal framework adapter pilot slices after the P43F pilot decision. Use when Codex evaluates OpenAI Agents SDK, LangGraph, or another orchestration framework behind AiGenerationFrameworkAdapter.v0.1 while preserving rollback, fake-first replay, P42 gates, public surface freeze, and production_ready false.
---

# Framework Adapter Pilot

## Workflow

1. Read the current decision and policy evidence first:
   - `docs/framework-adoption-decision-p43.md`
   - `spec/eval/p43_framework_adoption_contract.yaml`
   - `POLICY.md`
2. Keep the current Responses/httpx gateway and `BaselineResponsesFrameworkAdapter` as the rollback baseline.
3. Start with fake adapters and sanitized fixtures before any real framework dependency or live provider call.
4. Route candidate output through `AiJavaMyBatisDraftPack.v0.1`, deterministic inventory checks, and P42 Java/MyBatis quality gates.
5. Record candidate results as baseline-vs-candidate evidence, not as production adoption.

## Pilot Gates

- Do not install OpenAI Agents SDK, LangGraph, or another framework unless a separate dependency proposal and policy gate approves it.
- Do not add request flags, environment switches, public API fields, DB schema, UI, public MCP routes, or public artifact types.
- Do not store raw prompts, raw provider responses, raw SP definitions, raw guide body, row data, secrets, failed Java/XML payloads, or unredacted framework traces.
- Do not allow procedure execution, row-data queries, business DB DDL/DML, source apply, deploy, publish, or automatic conversion.
- Keep weak or unsupported framework-inferred facts as `REVIEW_REQUIRED`.
- Keep `production_ready` false until a separate production-readiness gate exists.

## Output Checklist

- Candidate framework id and version/source assumptions are documented.
- Rollback path is explicit and tested.
- Fake replay passes before live or dependency work is proposed.
- ManageBond is treated as a benchmark fixture only, never a runtime answer key.
- Failure diagnostics are sanitized, stage-specific, and do not include raw payloads.
