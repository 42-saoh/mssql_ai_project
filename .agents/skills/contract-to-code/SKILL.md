---
name: contract-to-code
description: Translate architecture contracts, OpenAPI, DDL, and policies into the smallest implementation slice.
---

# Trigger

Use this when a design document, API contract, or schema already exists and needs to become working code.

# Steps

1. Read the authoritative contract first.
2. Identify the narrowest end-to-end slice.
3. Implement only the contract portion needed for that slice.
4. Add or update tests for the slice.
5. Sync the related docs if behavior or commands changed.

# Adapter-First Slices

- For P43/P44 framework or orchestration work, keep new behavior behind internal adapter injection unless a contract explicitly authorizes a public surface.
- Preserve the current Responses/httpx gateway or documented baseline as the rollback path.
- Do not add request flags, environment switches, public API fields, DB schema, UI, public MCP routes, or artifact types inside a readiness slice.
- Keep candidate framework outputs behind existing schema, inventory, validation, repair, and quality gates.

# Checks

- Does the code still match the declared contract?
- Did you preserve approval and read-only boundaries?
- Did you avoid expanding scope into adjacent features?
- Did the slice keep `production_ready` false when the contract is readiness-only?
