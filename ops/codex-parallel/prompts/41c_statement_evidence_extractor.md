## Role
template_engineer / mcp_engineer with `contract-to-code` and `mcp-tooling-design`.

## Task
P41C: implement deterministic statement evidence extraction or a read-only MCP contract
for statement evidence. Keep it metadata-only and `production_ready: false`.

## Scope
- Extract sanitized statement ids, operation type, target ref, branch hints, parameter usage, column hints, and evidence refs.
- Keep extractor output compatible with `SpOperationModel.v0.1`.
- If an MCP tool is added, design it as structured-input-only with `snapshotId`, `collectedAt`, and `evidenceRefs`.

## Constraints
- No free-form SQL tool surface.
- No row data retrieval, procedure execution, business DB DDL/DML, raw SP definition storage, raw prompt storage, or raw provider response storage.
- Dynamic SQL, cross-DB writes, temp/table-variable uncertainty, and called procedure I/O stay `REVIEW_REQUIRED`.

## Acceptance
- The extractor can produce statement evidence for a fixture matching `PCO_GU_ManageBond_PRC` branch coverage.
- Any MCP addition has contract tests and read-only enforcement.
- No public invoke route is widened unless explicitly approved in a later task.
