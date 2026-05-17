# P38 Metadata Design Chat

## Goal

Add a durable metadata design chat flow that turns user-provided field names,
descriptions, and table hints into evidence-bound table script previews and
`DTO_DRAFT` previews.

## Contract

- Keep P37 metadata DTO preview behavior unchanged.
- Add `POST /api/v1/metadata/design-runs`,
  `GET /api/v1/metadata/design-runs/{runId}`, and
  `GET /api/v1/metadata/design-conversations/{conversationId}`.
- Store sanitized request/result/error JSON in manual-apply
  `dbo.METADATA_DESIGN_RUNS`.
- Use only read-only metadata MCP tools: `search_columns`, `search_tables`,
  `find_similar_tables`, and bounded table metadata tools.
- Generate `createTableScriptPreview`, not a workflow artifact or executable
  migration.
- Generate optional `DTO_DRAFT` preview inside the design run result only.

## Guardrails

- No row data access.
- No procedure execution.
- No business DB DDL/DML.
- No automatic DDL apply.
- No source apply/deploy/publish.
- No raw prompt, raw provider response, full SQL/SP definition, or secret storage.
- Do not revive public `DTO_MODEL_DRAFT`, `VO_DRAFT`, `MODEL_DRAFT`, or
  `DDL_DRAFT` outputs.

## Verification

```bash
make test PYTEST_ARGS="tests/unit/api/test_metadata_design_service.py tests/contract/test_openapi_and_env_sample_assets.py tests/unit/web/test_p14_product_ui_static.py"
make test-core
make test-web-smoke
```
