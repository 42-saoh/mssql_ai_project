---
name: framework-trace-policy-review
description: Review internal framework tool context, tracing, persistence, checkpointer, and storage-summary policy for AiGenerationFrameworkAdapter candidates. Use when Codex must prove no raw prompts, provider responses, SP text, guide body, row data, secrets, source apply, deploy, procedure execution, or unsafe Java/XML payloads can leak through OpenAI Agents SDK, LangGraph, or fake framework traces.
---

# Framework Trace Policy Review

## Workflow

1. Inspect the adapter policy helpers and tests around tool context, trace summaries, and storage records.
2. Confirm every framework stage receives only sanitized context: stage names, hashes, operation/DTO/statement ids or counts, deterministic inventory, allowed evidence refs, quality gates, and `REVIEW_REQUIRED` markers.
3. Confirm stored trace summaries contain only adapter ids, candidate framework ids, stage/status, component ids, counts, hashes, blocker or failure codes, and numeric policy-safe metrics.
4. Check OpenAI Agents SDK tracing and LangGraph persistence or checkpointer behavior against current official docs before any adopted-runtime change or live evidence run.
5. Report blockers before implementation proceeds.

## Blockers

- Raw prompt, provider response, SP definition, guide body, row data, secret, tool I/O, or failed Java/XML payload appears in context, trace, summary, fixture, docs, or storage.
- Candidate output bypasses P42 schema, deterministic inventory, repair, Java/MyBatis quality, or no-fallback gates.
- Framework persistence stores unredacted graph state, messages, tool calls, or provider payloads.
- Framework tracing is enabled without a proven redaction or sensitive-data exclusion boundary.
- Runtime source apply, deploy, procedure execution, row-data query, or business DB DDL/DML is implied or allowed.

## Output Checklist

- Findings include the blocker id, affected stage, and sanitized reproduction path.
- Safe summaries are described with hash/count/code fields only.
- Residual weak facts remain `REVIEW_REQUIRED`.
- `production_ready` remains false.
