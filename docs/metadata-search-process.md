# Metadata Search Process

Metadata search is a read-only metadata discovery flow for business-readable table and column descriptions.

- The Web `/metadata/search` page calls the Portal API `GET /api/v1/metadata/search`.
- The Portal API invokes the MSSQL Metadata MCP `search_metadata_objects` tool.
- `search_metadata_objects` may return object identity, evidence refs, caveats, blockers, and safe display fields such as table descriptions, column descriptions, data types, parent table summaries, and table column lists.
- The Web result cards render table/column labels and status messages, not technical evidence locators such as target keys, snapshot ids, or MCP locator strings.
- The flow does not use an LLM, prompt UI, metadata analysis action, row-data query, stored procedure execution, SQL definition text, DDL/DML, apply, publish, or deploy behavior.
