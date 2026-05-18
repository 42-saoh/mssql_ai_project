---
name: docs-sync
description: Synchronize architecture, policy, tools, and eval docs after code or contract changes.
---

# Trigger

Use this when commands, structure, API, schema, or policy changed.

# Steps

1. Identify the authoritative behavior from code or spec.
2. Update the minimum affected docs.
3. Fix examples and paths, not just prose.
4. Remove stale contradictions.
5. Leave a short summary of what was synchronized.

# Decision Gate Docs

- For framework or orchestration readiness work, include the decision, verification commands, quality comparison, policy findings, rollback path, and residual `REVIEW_REQUIRED` items.
- For P44+ actual runtime adoption and P47 quality uplift, document live evidence, sanitized blocker codes, generic coverage-first quality changes, benchmark-only metrics, and any blocked live path without exposing raw payloads.
- State explicitly when `production_ready` remains false.
- Do not imply automatic conversion, source apply, deploy, row-data access, procedure execution, or production adoption unless a separate gate approved it.
