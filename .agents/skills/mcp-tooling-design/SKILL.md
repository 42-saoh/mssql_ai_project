---
name: mcp-tooling-design
description: Design or refine read-only MSSQL Metadata MCP tools, schemas, evidence refs, errors, and contract tests.
---

# Trigger

Use this when adding or changing any MSSQL Metadata MCP tool.

# Steps

1. Confirm the tool belongs to metadata-only scope.
2. Define structured input fields and explicit output schema.
3. Include `snapshotId`, `collectedAt`, and `evidenceRefs` where applicable.
4. Model failure modes explicitly.
5. Add contract tests before adapter implementation if possible.

# Guardrails

- No free-form SQL tool surface.
- No row-data retrieval.
- No write-capable commands.
