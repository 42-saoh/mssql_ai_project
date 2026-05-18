## Role
reviewer / platform_worker with `quality-gate-review`, `mcp-tooling-design`, and `docs-sync`.

## Task
P43D: add policy gates for framework tool orchestration and trace handling. Keep
`production_ready: false`.

## Scope
- Define what framework tool calls may see: sanitized metadata, operation model
  summaries, deterministic inventory contract, allowed evidence refs, and review markers.
- Validate trace summaries store only stage names, component ids, counts, hashes,
  failure codes, and policy-safe metrics.
- Block raw prompt, raw provider response, raw SP full dump, raw guide body, row data,
  secrets, generated source apply, deploy, and business DB side-effect claims.
- Document any framework-specific tracing switches that must be disabled or redacted
  before adoption.

## Constraints
- No public MCP route expansion.
- No business DB row data, stored procedure execution, DDL/DML apply, source apply, or deploy.
- No production readiness claim.
- Do not store sensitive tracing payloads even in failed runs.

## Acceptance
- Trace and tool policy tests fail on raw content leakage and pass on sanitized hashes.
- Framework candidate traces cannot bypass P42/P43 storage policy.
- Remaining weak facts are marked `REVIEW_REQUIRED`.
- Docs identify framework tracing as a blocker until sanitization is proven.
