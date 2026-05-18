---
name: orchestration-migration-planning
description: Decompose a major post-P43 orchestration or framework migration into small reversible P44+ slices. Use when Codex plans a large transformation involving workflow orchestration, framework adoption, adapter migration, rollback strategy, A/B replay, decision gates, or production_ready false readiness work.
---

# Orchestration Migration Planning

## Workflow

1. State the transformation goal and the current rollback baseline.
2. Split the work into narrow slices: contract, fake harness, internal injection, policy gate, A/B replay, docs decision, then optional live evidence.
3. Keep each slice reversible and independently testable.
4. Require fixture-first evidence before live providers, live PPM, or framework dependencies.
5. Preserve public interfaces unless a separate contract explicitly authorizes expansion.

## Planning Guardrails

- Do not turn a pilot into adoption without a decision report and rollback evidence.
- Do not broaden public API, DB schema, UI, public MCP routes, or public artifact types inside a readiness slice.
- Do not infer metadata facts from generated code.
- Do not run procedures, query row data, apply business DB DDL/DML, write generated source into application trees, deploy, or publish.
- Keep unsupported or weak facts as `REVIEW_REQUIRED`.
- Keep `production_ready` false until a separate production-readiness gate exists.

## Output Checklist

- Slice order names the contract, implementation, tests, docs, and rollback proof.
- Baseline-vs-candidate comparison uses the same generic inventory contract.
- ManageBond appears only as benchmark evidence, with at least one synthetic guard for overfitting.
- Verification commands and residual risks are included.
