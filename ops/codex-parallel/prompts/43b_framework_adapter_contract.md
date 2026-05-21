## Role
architect / platform_worker with `contract-to-code` and `quality-gate-review`.

## Task
P43B: implement an internal `AiGenerationFrameworkAdapter.v0.1` contract and
fake-adapter harness. Keep `production_ready: false`.

## Scope
- Define the adapter protocol for staged inventory planning, file content drafting,
  repair, and sanitized trace summaries.
- Keep the current Responses/httpx gateway as the baseline adapter.
- Add fake adapters for candidate framework behavior without requiring live
  OpenAI, live PPM, OpenAI Agents SDK, LangGraph, or network access.
- Prove invalid adapter output cannot bypass P42 schema, inventory, and quality gates.

## Constraints
- Do not install a new framework dependency unless this slice explicitly adds a
  follow-up proposal and policy gate; default implementation must run without it.
- No public API, DB schema, UI, public MCP route, or public artifact type changes.
- No row data, procedure execution, business DB DDL/DML, source apply, deploy, raw
  prompt storage, or raw provider response storage.
- Framework traces must be sanitized to hashes, stage names, counts, and blocker ids.

## Acceptance
- Adapter protocol can represent baseline and candidate framework runs.
- Fake adapter tests cover valid output, schema failure, two-DTO collapse, missing
  `REVIEW_REQUIRED`, and raw trace leakage.
- The adapter does not weaken P42 deterministic gates.
- Storage-ready summaries contain sanitized structured output and trace hashes only.
